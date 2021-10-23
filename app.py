from flask import Flask, render_template
from anchorProtocol import getAnchorDeposits, calculateYield, getCurrentAUstExchangeRate

app = Flask(__name__)

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/address/<id>")
def anchorErningsForAdress(id):
    # call anchor ...
    deposits = getAnchorDeposits(id)
    currentRate = float(getCurrentAUstExchangeRate())
    totalYield = calculateYield(deposits, currentRate)
    deposits = [{'In': 1075.688451, 'Out': 1158.0, 'fee': 1.672663, 'feeUnit': 'ust', 'time': '2021-08-05T07:08:42Z'}, {'In': 55.831474, 'Out': 59.985, 'fee': 0.549374, 'feeUnit': 'ust', 'time': '2021-08-01T14:02:10Z'}]
    return render_template('anchorOverview.html', deposits = deposits, address=id, y=totalYield)