from flask import Flask, render_template
from anchorProtocol import getAnchorDeposits, calculateYield, getCurrentAUstExchangeRate

app = Flask(__name__)

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/address/<address>")
def anchorErningsForAdress(address):
    # call anchor ...
    deposits = getAnchorDeposits(address)
    currentRate = float(getCurrentAUstExchangeRate())
    totalYield = calculateYield(deposits, currentRate)
    return render_template('anchorOverview.html', deposits = deposits, address=address, y=totalYield)