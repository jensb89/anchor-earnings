from flask import Flask, render_template
from anchorProtocol import getAnchorDeposits, calculateYield, getCurrentAUstExchangeRate
import requests
import datetime

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

    # Add UTC time in s
    minTime = datetime.datetime.now()
    for deposit in deposits:
        deposit["unixTimestamp"] = datetime.datetime.strptime(deposit["time"], "%Y-%m-%dT%H:%M:%SZ")
        minTime = min(minTime, deposit["unixTimestamp"])
        deposit["rate"] = deposit["Out"] / deposit["In"]
    
    # Graph data
    histData = getHistData(deposits)

    # get Eur rate
    rateEurUsd = getEurUsdRateFromTerraPriceOracle()

    return render_template('anchorOverview.html', deposits = deposits, address=address, y=totalYield, h=histData, eurRate = rateEurUsd )


def getHistData(deposits):
    # we use flipside to get historical aust data. Is there a better way by using terra API directly ??
    res = requests.get("https://api.flipsidecrypto.com/api/v2/queries/1de96d09-4d77-4ad7-b0c8-e907e86fdcb7/data/latest")
    res = res.json()
    histYields = []
    for elem in res:
        timeStr = elem["DAYTIMESTAMP"]
        time = datetime.datetime.strptime(timeStr, "%Y-%m-%dT%H:%M:%SZ")
        austVal = elem["AUST_VALUE"]
        
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
