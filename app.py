import os
import pandas as pd
import pyodbc
from flask import Flask, request, render_template_string, flash, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
import io

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default-secret-key')

# -------------------------------------------------------
# Azure SQL DB CONFIG
# -------------------------------------------------------
DB_SERVER = os.environ.get('DB_SERVER', 'earthquake-server.database.windows.net')
DB_DATABASE = os.environ.get('DB_DATABASE', 'earthquake-db')
DB_USERNAME = os.environ.get('DB_USERNAME', 'kofiboadu11')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'B@kugan1')

# -------------------------------------------------------
# MAIN INDEX PAGE (Upload + Query + Visualization Button)
# -------------------------------------------------------
INDEX_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title>Earthquake Data Manager</title>
<style>
body { font-family: Arial; margin: 40px; }
.container { max-width: 900px; margin: auto; }
button { padding: 10px 20px; background: #007bff; color: white; border: none; cursor: pointer; margin-top: 10px; }
button:hover { background: #0056b3; }
textarea { width: 100%; height: 120px; }
.flash { padding: 10px; margin: 10px 0; border-radius: 4px; }
.flash.success { background: #d4edda; }
.flash.error { background: #f8d7da; }
.query-button { background: #28a745; margin: 5px; }
.nav-button { background: #6c63ff; }
</style>
</head>
<body>

<div class="container">
<h1>Earthquake Data Manager</h1>

{% with messages = get_flashed_messages(with_categories=true) %}
{% if messages %}
{% for category, message in messages %}
<div class="flash {{ category }}">{{ message }}</div>
{% endfor %}
{% endif %}
{% endwith %}

<h2>Upload CSV File</h2>
<form action="{{ url_for('upload_csv') }}" method="post" enctype="multipart/form-data">
<input type="file" name="csv_file" accept=".csv" required>
<button type="submit">Upload</button>
</form>

<h2>Execute SQL Query</h2>
<form action="{{ url_for('execute_query') }}" method="post">
<textarea name="sql_query" placeholder="SELECT TOP 10 * FROM earthquakes"></textarea>
<button type="submit">Run Query</button>
</form>

<h2>Visualization</h2>
<a href="/visualize"><button class="nav-button">Open Visualization Dashboard</button></a>

<h3>Sample Queries</h3>
<button class="query-button" onclick="fillQuery('SELECT TOP 10 * FROM earthquakes ORDER BY mag DESC')">Top 10 Magnitudes</button>
<button class="query-button" onclick="fillQuery('SELECT mag, COUNT(*) AS count FROM earthquakes GROUP BY mag ORDER BY mag')">Magnitude Histogram</button>
<button class="query-button" onclick="fillQuery('SELECT mag, depth FROM earthquakes')">Magnitude vs Depth</button>

</div>

<script>
function fillQuery(q) {
  document.querySelector('textarea[name="sql_query"]').value = q;
}
</script>

</body>
</html>
"""

# -------------------------------------------------------
# RESULTS TABLE (same as before)
# -------------------------------------------------------
RESULTS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title>Results</title>
<style>
body { font-family: Arial; margin: 40px; }
table { width: 100%; border-collapse: collapse; margin-top: 20px; }
th, td { border: 1px solid #ddd; padding: 8px; }
th { background: #f2f2f2; }
button { padding: 10px 20px; background: #6c757d; color: white; border: none; }
</style>
</head>
<body>
<a href="/" class="back-button"><button>Back</button></a>
<h2>Results ({{ row_count }} rows)</h2>
<div><strong>Query:</strong> {{ query }}</div>

{% if results %}
<table>
<thead><tr>
{% for col in columns %}
<th>{{ col }}</th>
{% endfor %}
</tr></thead>

<tbody>
{% for row in results %}
<tr>
{% for col in columns %}
<td>{{ row[col] }}</td>
{% endfor %}
</tr>
{% endfor %}
</tbody>
</table>

{% else %}
<p>No results.</p>
{% endif %}
</body>
</html>
"""

# -------------------------------------------------------
# VISUALIZATION DASHBOARD (Chart.js)
# -------------------------------------------------------
VISUAL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title>Visualization Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body { font-family: Arial; margin: 40px; }
.container { max-width: 1000px; margin: auto; }
canvas { margin-top: 30px; }
button { padding: 8px 18px; background: #007bff; color: white; border: none; }
select, textarea { width: 100%; padding: 10px; margin-top: 10px; }
</style>
</head>
<body>

<div class="container">
<h1>Earthquake Visualization Dashboard</h1>

<a href="/"><button>Back</button></a>

<h3>Enter SQL Query</h3>
<textarea id="sql">SELECT mag, COUNT(*) AS count FROM earthquakes GROUP BY mag ORDER BY mag</textarea>
<button onclick="runQuery()">Visualize</button>

<h3>Chart Type</h3>
<select id="chartType">
<option value="bar">Bar Chart</option>
<option value="pie">Pie Chart</option>
<option value="scatter">Scatter Plot</option>
</select>

<canvas id="chartCanvas" width="900" height="450"></canvas>
</div>

<script>
let chartRef = null;

function runQuery() {
    fetch('/visualize-query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sql: document.getElementById('sql').value })
    })
    .then(res => res.json())
    .then(data => drawChart(data))
}

function drawChart(data) {
    if (chartRef) chartRef.destroy();

    const ctx = document.getElementById('chartCanvas');

    const labels = data.labels;
    const values = data.values;

    const type = document.getElementById("chartType").value;

    let chartData = {};

    if (type === "scatter") {
        chartData = {
            datasets: [{
                label: "Scatter Plot",
                data: labels.map((x, i) => ({ x: x, y: values[i] })),
                pointRadius: 5
            }]
        };
    } else {
        chartData = {
            labels: labels,
            datasets: [{
                label: "Results",
                data: values
            }]
        };
    }

    chartRef = new Chart(ctx, {
        type: type,
        data: chartData,
        options: { responsive: true }
    });
}
</script>

</body>
</html>
"""

# -------------------------------------------------------
# DATABASE CONNECTION
# -------------------------------------------------------
def get_connection_string():
    drivers = ["ODBC Driver 18 for SQL Server","ODBC Driver 17 for SQL Server"]
    available = pyodbc.drivers()
    driver = next((d for d in drivers if d in available), available[0])
    return f"DRIVER={{{driver}}};SERVER={DB_SERVER};DATABASE={DB_DATABASE};UID={DB_USERNAME};PWD={DB_PASSWORD};Encrypt=yes;TrustServerCertificate=no;"

def get_db_connection():
    try:
        conn = pyodbc.connect(get_connection_string())
        return conn
    except Exception as e:
        print("DB Error:", e)
        return None

# -------------------------------------------------------
# MAIN ROUTES
# -------------------------------------------------------
@app.route("/")
def index():
    return render_template_string(INDEX_TEMPLATE)

# -------------------------------------------------------
# VISUALIZATION ROUTES
# -------------------------------------------------------
@app.route("/visualize")
def visualize():
    return render_template_string(VISUAL_TEMPLATE)

@app.route("/visualize-query", methods=["POST"])
def visualize_query():
    data = request.get_json()
    query = data.get("sql")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query)

    cols = [c[0] for c in cur.description]
    rows = cur.fetchall()

    labels = [row[0] for row in rows]
    values = [row[1] for row in rows]

    return jsonify({"labels": labels, "values": values})

# -------------------------------------------------------
# UPLOAD CSV (UNCHANGED FROM YOURS)
# -------------------------------------------------------
@app.route('/upload', methods=['POST'])
def upload_csv():
    if 'csv_file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('index'))

    file = request.files['csv_file']
    df = pd.read_csv(file)
    df = df.dropna(subset=['latitude', 'longitude', 'mag'])

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM earthquakes")
    conn.commit()

    insert_sql = """
    INSERT INTO earthquakes (latitude, longitude, depth, mag)
    VALUES (?, ?, ?, ?)
    """

    for _, row in df.iterrows():
        cursor.execute(insert_sql, row['latitude'], row['longitude'], row['depth'], row['mag'])

    conn.commit()
    conn.close()

    flash(f"Uploaded {len(df)} rows!", "success")
    return redirect(url_for('index'))

# -------------------------------------------------------
# SQL QUERY (TABLE OUTPUT)
# -------------------------------------------------------
@app.route('/query', methods=['POST'])
def execute_query():
    query = request.form.get('sql_query')

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query)

    cols = [c[0] for c in cur.description]
    rows = cur.fetchall()

    results = [dict(zip(cols, r)) for r in rows]

    return render_template_string(RESULTS_TEMPLATE,
        columns=cols, results=results, query=query, row_count=len(results)
    )

# -------------------------------------------------------
# RUN
# -------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
