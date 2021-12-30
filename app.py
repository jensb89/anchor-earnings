from flask import Flask, render_template,request,redirect,json
from anchorProtocol import getAnchorDeposits, calculateYield, getCurrentAUstExchangeRate, getClosestHistoricalRate
import requests
import datetime
from werkzeug.exceptions import HTTPException
from cachetools import cached, TTLCache

cache = TTLCache(maxsize=100, ttl=7200)
app = Flask(__name__)

@app.route("/")
def index():
        return render_template('index.html')

@app.errorhandler(HTTPException)
def handle_exception(e):
    """Return JSON instead of HTML for HTTP errors."""
    # start with the correct headers and status code from the error
    response = e.get_response()
    # replace the body with JSON
    response.data = json.dumps({
        "code": e.code,
        "name": e.name,
        "description": e.description,
    })
    response.content_type = "application/json"
    return response

@app.route("/redirectToWallet", methods = ['POST', 'GET'])
def redirectToWallet():
    if request.method == 'POST':
        wallet = request.form['walletAddress']
        print(wallet)
        return redirect(f"/address/{wallet}")

@app.route("/address/<address>")
def anchorErningsForAdress(address):

    # First, we query all historical rates. We need them for the plot and to calculate the yield for aUST transfers
    historicalRates = getHistoricalAUstRate()

    error = ""
    # call anchor ...
    try:
        deposits,warnings = getAnchorDeposits(address)
        currentRate = float(getCurrentAUstExchangeRate())
        totalYield = calculateYield(deposits, currentRate, historicalRates)
    except AssertionError:
        error = "Something went wrong with parsing the data. Please open a ticket: https://github.com/jensb89/anchor-earnings/issues"
        deposits = []
        totalYield = {'yield': 0, 'ustHoldings': 0, 'aUSTHoldings': 0}
        currentRate = 0
    except BaseException:
        error = "Something went wrong. Please open a ticket:  https://github.com/jensb89/anchor-earnings/issues"
        deposits = []
        totalYield = {'yield': 0, 'ustHoldings': 0, 'aUSTHoldings': 0}
        currentRate = 0
    #todo: requests.exceptions.ConnectionError
    
    # Add UTC time in s
    minTime = datetime.datetime.now()
    for deposit in deposits:
        deposit["unixTimestamp"] = datetime.datetime.strptime(deposit["time"], "%Y-%m-%dT%H:%M:%SZ")
        minTime = min(minTime, deposit["unixTimestamp"])
        deposit["rate"] = deposit["Out"] / deposit["In"] if deposit["Out"] != 0 else getClosestHistoricalRate(historicalRates, deposit["time"])
    
    # Graph data
    histData = getHistData(deposits, historicalRates)

    # get Eur rate
    rateEurUsd = getEurUsdRateFromTerraPriceOracle()

    return render_template('anchorOverview.html', deposits = deposits, address=address, y=totalYield, h=histData, eurRate = rateEurUsd, error=error, warnings=warnings )

@cached(cache)
def getHistoricalAUstRate():
    # we use flipside to get historical aust data. Is there a better way by using terra API directly ??
    res = requests.get("https://api.flipsidecrypto.com/api/v2/queries/1de96d09-4d77-4ad7-b0c8-e907e86fdcb7/data/latest")
    res = res.json()
    arr = []
    for elem in res:
        time = datetime.datetime.fromisoformat(elem["DAYTIMESTAMP"])
        arr.append((time, elem["AUST_VALUE"]))
    return arr

def getHistData(deposits, historicalRates):
    histYields = []
    for elem in historicalRates:
        time = elem[0]
        austVal = elem[1]
        timeStr = datetime.datetime.strftime(time, "%Y-%m-%d")
        
        startDateReached = True
        histYield = 0
        for deposit in deposits:
            if deposit["unixTimestamp"] > time:
                continue
            histYield += (austVal - deposit["rate"]) * deposit["In"]
            startDateReached = False
        
        histYields.append({"time":timeStr, "yield":histYield})

        if startDateReached:
            return histYields
    
    return histYields

def getEurUsdRateFromTerraPriceOracle():
    response = requests.get("https://lcd.terra.dev/oracle/denoms/exchange_rates")
    if response.status_code == 200:
        ret = response.json()
        terraEur = 1
        terraUsd = 1
        for terraPrice in ret["result"]:
            if terraPrice["denom"] == "ueur":
                terraEur = float(terraPrice["amount"])
            if terraPrice["denom"] == "uusd":
                terraUsd = float(terraPrice["amount"])
        if terraEur == 0 or terraUsd == 0:
            return None
        return terraEur / terraUsd
    elif response.status_code == 404:
        print('Not Found.')
    else:
        raise Exception("Response failed!")
