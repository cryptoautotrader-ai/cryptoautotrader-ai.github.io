import dash
import threading
from dash import dcc, html
from dash.dependencies import Input, Output
from waitress import serve
import plotly.graph_objs as go

# Dash app initialization
app = dash.Dash(__name__, server=True, update_title="")
app.title = "Crypto Autotrader Dashboard"

# Thread-safe global data storage
_data_lock = threading.Lock()
_info_messages = []
_memory_messages = []
_transaction_costs = []

X = 1024 * 1024


# Thread-safe functions for modifying data
def add_transaction_cost(cost: float):
    """Thread-safe function to add a transaction cost."""
    with _data_lock:
        _transaction_costs.append(cost)
        if len(_transaction_costs) > 50:
            _transaction_costs.pop(0)


def add_info_message(message: str):
    """Thread-safe function to add an info message."""
    with _data_lock:
        _info_messages.append(message)


def add_memory_messages(memory_message: str):
    """Thread-safe function to add an info message."""
    with _data_lock:
        _memory_messages.append(memory_message)
        if len(_memory_messages) > 1:
            _memory_messages.pop(0)


def get_transaction_costs():
    """Thread-safe function to retrieve transaction costs."""
    with _data_lock:
        return list(_transaction_costs)


def get_info_messages():
    """Thread-safe function to retrieve info messages."""
    with _data_lock:
        return list(_info_messages)


def get_memory_messages():
    """Thread-safe function to retrieve info messages."""
    with _data_lock:
        return list(_memory_messages)


# Define Dashboard Layout
app.layout = html.Div([
    html.H1("Crypto Autotrader Dashboard", style={'textAlign': 'center'}),

    # Memory Usage Display
    html.Div([
        html.H3("Memory Usage"),
        html.P(id="memory-usage", style={'fontSize': '20px', 'color': 'blue'})
    ], style={'border': '2px solid #ddd', 'padding': '10px', 'margin': '10px'}),

    # Transaction Cost Chart
    html.Div([
        html.H3("Transaction Cost Over Time"),
        dcc.Graph(id="transaction-cost-chart")
    ], style={'border': '2px solid #ddd', 'padding': '10px', 'margin': '10px'}),

    # Notifications
    html.Div([
        html.H3("Latest Notifications"),
        html.Ul(id="info-messages")
    ], style={'border': '2px solid #ddd', 'padding': '10px', 'margin': '10px'}),

    # Live update intervals
    dcc.Interval(id="interval-component", interval=10000, n_intervals=0)
])


# Callback to update memory usage
@app.callback(
    Output("memory-usage", "children"),
    [Input("interval-component", "n_intervals")]
)
def update_memory_usage(_):
    return get_memory_messages()[-1]


# Callback to update transaction cost chart
@app.callback(
    Output("transaction-cost-chart", "figure"),
    [Input("interval-component", "n_intervals")]
)
def update_transaction_cost_chart(_):
    transaction_costs = get_transaction_costs()
    fig = go.Figure()

    if transaction_costs:
        fig.add_trace(go.Scatter(
            y=transaction_costs, mode="lines+markers", name="Transaction Cost",
            line=dict(color="green")
        ))
    else:
        fig.add_trace(go.Scatter(y=[], mode="lines+markers", name="No Data"))

    fig.update_layout(
        title="Transaction Costs Over Time",
        xaxis_title="Transaction Count",
        yaxis_title="Cost",
        template="plotly_dark"
    )
    return fig


# Callback to update info messages
@app.callback(
    Output("info-messages", "children"),
    [Input("interval-component", "n_intervals")]
)
def update_info_messages(_):
    messages = get_info_messages()
    return [html.Li(msg) for msg in messages[-10:]]


def run_dashboard():
    """Starts the Dash server in a separate thread."""
    threading.Thread(target=lambda: serve(
        app=app.server,
        host="0.0.0.0", port=8050
    ), daemon=True).start()
