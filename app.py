import os
import pandas as pd
import pyodbc
from flask import Flask, request, render_template_string, flash, redirect, url_for, jsonify, session
from werkzeug.utils import secure_filename
import io

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default-secret-key')

# -------------------------------------------------------
# Azure SQL DB CONFIG (left in place)
# -------------------------------------------------------
DB_SERVER = os.environ.get('DB_SERVER', 'earthquake-server.database.windows.net')
DB_DATABASE = os.environ.get('DB_DATABASE', 'earthquake-db')
DB_USERNAME = os.environ.get('DB_USERNAME', 'kofiboadu11')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'B@kugan1')

# -------------------------------------------------------
# In-memory dataset and helper
# -------------------------------------------------------
# We'll store a DataFrame in a global variable for the sample data and filtering.
DATA_DF = pd.DataFrame(
    [
        {"Amount": 10, "Food": "Apples", "Category": "F"},
        {"Amount": 2,  "Food": "Bananas", "Category": "F"},
        {"Amount": 40, "Food": "Cherries", "Category": "F"},
        {"Amount": 1,  "Food": "Daikon", "Category": "V"},
        {"Amount": 10, "Food": "Fig", "Category": "F"},
        {"Amount": 50, "Food": "Grapes", "Category": "F"},
        {"Amount": 5,  "Food": "Peach", "Category": "F"},
        {"Amount": 12, "Food": "Celery", "Category": "V"},
        {"Amount": 25, "Food": "Watermelon", "Category": "F"},
    ]
)

# -------------------------------------------------------
# MAIN INDEX PAGE (Upload + Query + Visualization Button + new Charts UI)
# -------------------------------------------------------
INDEX_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title> Food Chart Manager</title>
<style>
body { font-family: Arial; margin: 24px; }
.container { max-width: 1000px; margin: auto; }
button { padding: 8px 16px; background: #007bff; color: white; border: none; cursor: pointer; margin: 6px 0; }
button:hover { opacity: 0.9; }
textarea, input[type=text], input[type=number] { width: 100%; padding: 8px; margin-top: 6px; box-sizing: border-box; }
.flash { padding: 10px; margin: 10px 0; border-radius: 4px; }
.flash.success { background: #d4edda; }
.flash.error { background: #f8d7da; }
.table { width: 100%; border-collapse: collapse; margin-top: 12px; }
.table th, .table td { border: 1px solid #ddd; padding: 8px; }
.small { font-size: 0.9em; color: #555; }
.controls { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-top:10px; }
.control { flex: 1; min-width: 180px; }
</style>
</head>
<body>
<div class="container">
<h1> Charts</h1>

{% with messages = get_flashed_messages(with_categories=true) %}
{% if messages %}
{% for category, message in messages %}
<div class="flash {{ category }}">{{ message }}</div>
{% endfor %}
{% endif %}
{% endwith %}



<hr>
<h2>Charts & Inputs</h2>




<h3>Current Sample Data</h3>
<div id="sample-data">
  <table class="table">
    <thead><tr><th>Amount</th><th>Food</th><th>Category</th></tr></thead>
    <tbody>
    {% for _, row in sample.iterrows() %}
      <tr><td>{{ row.Amount }}</td><td>{{ row.Food }}</td><td>{{ row.Category }}</td></tr>
    {% endfor %}
    </tbody>
  </table>
</div>

<hr>
<a href="/charts"><button>Open Chart Dashboard</button></a>

</div>
</body>
</html>
"""

# -------------------------------------------------------
# CHARTS DASHBOARD TEMPLATE
# -------------------------------------------------------
CHARTS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title>Chart Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.3.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js"></script>
<style>
body { font-family: Arial; margin: 20px; }
.container { max-width: 1100px; margin: auto; }
.controls { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:12px; }
.controls .control { min-width: 140px; }
canvas { display:block; margin: 12px auto; }
/* Pie should occupy between 80% and 90% of screen width */
.pie-container { width: 85vw; max-width: 980px; margin: 0 auto; }
/* Bar should occupy between 70% and 90% of screen width */
.bar-container { width: 80vw; max-width: 980px; margin: 0 auto; }
/* Scatter uses a more compact width */
.scatter-container { width: 75vw; max-width: 980px; margin: 0 auto; }

textarea { width: 100%; min-height: 120px; }
button { padding: 8px 14px; background: #007bff; color: white; border: none; cursor:pointer; margin-top: 6px; }
</style>
</head>
<body>
<div class="container">
  <a href="/"><button>Back</button></a>
  <h1>Visualization Dashboard</h1>

  <section>
    <h2>Pie Chart (amount range filter)</h2>
    <div class="controls">
      <div class="control">
        <label>Min Amount</label>
        <input id="pie-min" type="number" value="5">
      </div>
      <div class="control">
        <label>Max Amount</label>
        <input id="pie-max" type="number" value="20">
      </div>
      <div class="control">
        <label>Category (optional)</label>
        <input id="pie-cat" type="text" placeholder="F or V or leave blank">
      </div>
      <div class="control">
        <label>&nbsp;</label><br>
        <button onclick="renderPie()">Visualize Pie</button>
      </div>
    </div>

    <div class="pie-container">
      <canvas id="pieCanvas" height="500"></canvas>
    </div>
  </section>

  <hr>

  <section>
    <h2>Bar Chart (amount range filter) — largest at top</h2>
    <div class="controls">
      <div class="control">
        <label>Min Amount</label>
        <input id="bar-min" type="number" value="5">
      </div>
      <div class="control">
        <label>Max Amount</label>
        <input id="bar-max" type="number" value="50">
      </div>
      <div class="control">
        <label>Category (optional)</label>
        <input id="bar-cat" type="text" placeholder="F or V or leave blank">
      </div>
      <div class="control">
        <label>&nbsp;</label><br>
        <button onclick="renderBar()">Visualize Bar</button>
      </div>
    </div>

    <div class="bar-container">
      <canvas id="barCanvas" height="600"></canvas>
    </div>
  </section>

  <hr>

  <section>
    <h2>Scatter (up to 10 lines of X,Y,C)</h2>
    <p class="small">Enter up to 10 lines, format: <strong>X,Y,C</strong> where X and Y are integers 0–499 and C in {1,2,3} (1=Green, 2=Black, 3=Red)</p>
    <textarea id="scatter-input" placeholder="e.g. 12,34,1\n200,300,3\n0,0,2"></textarea>
    <div style="margin-top:8px;">
      <button onclick="renderScatter()">Plot Scatter</button>
    </div>

    <div class="scatter-container">
      <canvas id="scatterCanvas" width="900" height="500"></canvas>
    </div>
  </section>
</div>

<script>
let pieChart = null;
let barChart = null;
let scatterChart = null;

Chart.register(ChartDataLabels);

// Helper to call our server endpoints
async function postJSON(url, payload) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return res.json();
}

/* -------------------- PIE -------------------- */
async function renderPie() {
  const min = parseFloat(document.getElementById('pie-min').value || 0);
  const max = parseFloat(document.getElementById('pie-max').value || 999999);
  const cat = (document.getElementById('pie-cat').value || '').trim();

  const data = await postJSON('/api/pie', { min, max, category: cat });

  if (pieChart) pieChart.destroy();
  const ctx = document.getElementById('pieCanvas');

  pieChart = new Chart(ctx, {
    type: 'pie',
    data: {
      labels: data.labels,
      datasets: [{
        data: data.values,
        /* generate distinct colors */
        backgroundColor: data.colors
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: {
          position: 'right', // show food names outside slices on right
          labels: {
            boxWidth: 12,
            padding: 12
          }
        },
        datalabels: {
          // show percent inside each slice
          formatter: (value, ctx) => {
            const sum = ctx.chart.data.datasets[0].data.reduce((a,b)=>a+b,0);
            if (!sum) return '';
            let pct = (value / sum) * 100;
            return pct.toFixed(1) + '%';
          },
          color: '#fff',
          anchor: 'center',
          align: 'center',
          font: {
            weight: 'bold',
            size: 14
          }
        },
        tooltip: { enabled: true }
      }
    }
  });
}

/* -------------------- BAR -------------------- */
async function renderBar() {
  const min = parseFloat(document.getElementById('bar-min').value || 0);
  const max = parseFloat(document.getElementById('bar-max').value || 999999);
  const cat = (document.getElementById('bar-cat').value || '').trim();

  const data = await postJSON('/api/bar', { min, max, category: cat });

  if (barChart) barChart.destroy();
  const ctx = document.getElementById('barCanvas');

  // We render a horizontal bar chart so largest is at top (indexAxis: 'y').
  barChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.labels, // in order: largest -> smallest
      datasets: [{
        label: 'Amount',
        data: data.values,
        backgroundColor: data.colors,
        borderWidth: 1
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      scales: {
        x: {
          beginAtZero: true
        },
        y: {
          ticks: { autoSkip: false }
        }
      },
      plugins: {
        legend: { display: false },
        datalabels: {
          // We will show two datalabels by customizing display and alignment using context:
          formatter: (value, ctx) => {
            // For inside-right of bar: show Food name (label)
            return ctx.chart.data.labels[ctx.dataIndex];
          },
          color: '#ffffff',
          anchor: 'end', // inside right side of bar
          align: 'right',
          clamp: true,
          font: { weight: '600' },
          listeners: {
            // prevent label clipping
            enter: function() {},
            leave: function() {}
          }
        },
        // show amount as well, outside left of each bar using a custom second plugin-like datalabels instance:
        customAmountLabels: {
          display: true
        }
      },
      // We'll add a plugin to draw the amounts on the left of bars (outside)
      plugins: [{
        id: 'amountsOnLeft',
        afterDatasetsDraw: function(chart, args, options) {
          const ctx = chart.ctx;
          chart.data.datasets.forEach(function(dataset, dsIndex) {
            const meta = chart.getDatasetMeta(dsIndex);
            meta.data.forEach(function(bar, index) {
              const val = dataset.data[index];
              // compute x,y for left-outside
              const x = bar.x - 6; // a bit left
              const y = bar.y;
              ctx.save();
              ctx.fillStyle = '#000';
              ctx.font = 'bold 12px Arial';
              ctx.textAlign = 'right';
              ctx.textBaseline = 'middle';
              ctx.fillText(String(val), x, y);
              ctx.restore();
            });
          });
        }
      }]
    },
    plugins: [ChartDataLabels]
  });
}

/* -------------------- SCATTER -------------------- */
async function renderScatter() {
  const raw = document.getElementById('scatter-input').value.trim();
  const lines = raw.split('\\n').map(l => l.trim()).filter(l => l.length>0).slice(0,10);
  const sets = lines.map(l => {
    const parts = l.split(',').map(p=>p.trim());
    if (parts.length !== 3) return null;
    return { x: parseInt(parts[0],10), y: parseInt(parts[1],10), c: parseInt(parts[2],10) };
  }).filter(s => s && !isNaN(s.x) && !isNaN(s.y) && !isNaN(s.c));

  const data = await postJSON('/api/scatter', { points: sets });

  if (scatterChart) scatterChart.destroy();
  const ctx = document.getElementById('scatterCanvas');

  scatterChart = new Chart(ctx, {
    type: 'scatter',
    data: {
      datasets: data.datasets
    },
    options: {
      responsive: true,
      scales: {
        x: {
          type: 'linear',
          min: 0,
          max: 499,
          title: { display: true, text: 'X' },
          ticks: { stepSize: 50 }
        },
        y: {
          type: 'linear',
          min: 0,
          max: 499,
          title: { display: true, text: 'Y' },
          ticks: { stepSize: 50 }
        }
      },
      plugins: {
        legend: { display: true }
      }
    }
  });
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
# DATABASE CONNECTION (unchanged)
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
# Routes
# -------------------------------------------------------
@app.route("/")
def index():
    # render sample data table
    return render_template_string(INDEX_TEMPLATE, sample=DATA_DF)

@app.route("/charts")
def charts():
    return render_template_string(CHARTS_TEMPLATE)

# Endpoint to "load sample" and raise hand
@app.route("/load-sample", methods=["POST"])
def load_sample():
    # in this demo the DATA_DF is already the sample, but we flash the message requested
    flash("✋ Hand raised — sample data loaded", "success")
    return redirect(url_for("index"))

# -------------------------------------------------------
# API endpoints for charts
# -------------------------------------------------------
import random
def _distinct_colors(n):
    # generate n visually distinct colors (simple approach)
    base = [
        "#3366CC","#DC3912","#FF9900","#109618","#990099",
        "#0099C6","#DD4477","#66AA00","#B82E2E","#316395",
        "#994499","#22AA99","#AAAA11","#6633CC","#E67300"
    ]
    if n <= len(base):
        return base[:n]
    out = base[:]
    while len(out) < n:
        out.append("#%06x" % random.randint(0,0xFFFFFF))
    return out[:n]

@app.route("/api/pie", methods=["POST"])
def api_pie():
    body = request.get_json() or {}
    min_amt = float(body.get("min", -1e9))
    max_amt = float(body.get("max", 1e9))
    cat = (body.get("category") or "").strip()
    df = DATA_DF.copy()
    df = df[(df["Amount"] >= min_amt) & (df["Amount"] <= max_amt)]
    if cat:
        df = df[df["Category"].astype(str).str.upper() == cat.upper()]
    # group by food (sum amounts if duplicates)
    dfg = df.groupby("Food", as_index=False)["Amount"].sum()
    if dfg.empty:
        return jsonify({"labels": [], "values": [], "colors": []})
    labels = dfg["Food"].tolist()
    values = dfg["Amount"].astype(float).tolist()
    colors = _distinct_colors(len(labels))
    return jsonify({"labels": labels, "values": values, "colors": colors})

@app.route("/api/bar", methods=["POST"])
def api_bar():
    body = request.get_json() or {}
    min_amt = float(body.get("min", -1e9))
    max_amt = float(body.get("max", 1e9))
    cat = (body.get("category") or "").strip()
    df = DATA_DF.copy()
    df = df[(df["Amount"] >= min_amt) & (df["Amount"] <= max_amt)]
    if cat:
        df = df[df["Category"].astype(str).str.upper() == cat.upper()]
    dfg = df.groupby("Food", as_index=False)["Amount"].sum()
    if dfg.empty:
        return jsonify({"labels": [], "values": [], "colors": []})
    # sort descending so largest at top
    dfg = dfg.sort_values(by="Amount", ascending=False)
    labels = dfg["Food"].tolist()
    values = dfg["Amount"].astype(float).tolist()
    # bars green as requested (use slightly varying shades if desired)
    base_green = "#2e8b57"
    colors = [base_green for _ in labels]
    return jsonify({"labels": labels, "values": values, "colors": colors})

@app.route("/api/scatter", methods=["POST"])
def api_scatter():
    body = request.get_json() or {}
    points = body.get("points", [])
    # Accept up to 10 points
    pts = (points or [])[:10]
    # color mapping: 1->green,2->black,3->red
    cmap = {1: "green", 2: "black", 3: "red"}
    # We'll create 3 datasets (one per color) for Chart.js
    datasets = []
    grouped = {1: [], 2: [], 3: []}
    for p in pts:
        try:
            x = int(p.get("x", p[0] if isinstance(p, (list,tuple)) else 0))
            y = int(p.get("y", p[1] if isinstance(p, (list,tuple)) else 0))
            c = int(p.get("c", p[2] if isinstance(p, (list,tuple)) else 1))
        except Exception:
            continue
        if c not in (1,2,3): c = 1
        if 0 <= x <= 499 and 0 <= y <= 499:
            grouped[c].append({"x": x, "y": y})

    color_names = {1: "Green (1)", 2:"Black (2)", 3:"Red (3)"}
    for k in (1,2,3):
        if grouped[k]:
            datasets.append({
                "label": color_names[k],
                "data": grouped[k],
                "pointRadius": 6,
                "backgroundColor": cmap[k]
            })

    return jsonify({"datasets": datasets})

# -------------------------------------------------------
# UPLOAD CSV (unchanged from user's original but route name kept)
# -------------------------------------------------------
@app.route('/upload', methods=['POST'])
def upload_csv():
    if 'csv_file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('index'))

    file = request.files['csv_file']
    try:
        df = pd.read_csv(file)
    except Exception as e:
        flash(f"Error reading CSV: {e}", "error")
        return redirect(url_for('index'))

    # For safety, require columns we need
    if not set(['latitude','longitude','mag']).issubset(df.columns):
        flash("CSV missing required columns: latitude, longitude, mag", "error")
        return redirect(url_for('index'))

    df = df.dropna(subset=['latitude', 'longitude', 'mag'])

    conn = get_db_connection()
    if conn is None:
        flash("DB connection failed; cannot upload", "error")
        return redirect(url_for('index'))

    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM earthquakes")
        conn.commit()

        insert_sql = """
        INSERT INTO earthquakes (latitude, longitude, depth, mag)
        VALUES (?, ?, ?, ?)
        """
        for _, row in df.iterrows():
            # provide default for depth if missing
            depth_val = row.get('depth', None)
            cursor.execute(insert_sql, row['latitude'], row['longitude'], depth_val, row['mag'])

        conn.commit()
    except Exception as e:
        flash(f"DB error while inserting: {e}", "error")
        return redirect(url_for('index'))
    finally:
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
    if conn is None:
        flash("DB connection failed; cannot execute query", "error")
        return redirect(url_for('index'))

    cur = conn.cursor()
    try:
        cur.execute(query)
    except Exception as e:
        flash(f"SQL execution error: {e}", "error")
        conn.close()
        return redirect(url_for('index'))

    cols = [c[0] for c in cur.description] if cur.description else []
    rows = cur.fetchall()
    results = [dict(zip(cols, r)) for r in rows]

    conn.close()
    return render_template_string(RESULTS_TEMPLATE,
        columns=cols, results=results, query=query, row_count=len(results)
    )

# -------------------------------------------------------
# RUN
# -------------------------------------------------------
if __name__ == "__main__":
    # For cloud deployments, you may want to set host and port differently.
    app.run(host="0.0.0.0", port=8000, debug=True)
