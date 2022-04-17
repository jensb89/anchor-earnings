from flask import Flask, render_template,request,redirect,json,url_for,jsonify,abort
from anchorProtocol import TooManyRequests, calculateYield, getCurrentAUstExchangeRate, getClosestHistoricalRate, AnchorProtocolHandler
import requests
import datetime
from werkzeug.exceptions import HTTPException
from cachetools import cached, TTLCache

from celery import Celery
#http://clouddatafacts.com/heroku/heroku-flask-redis/flask_redis.html
#https://blog.miguelgrinberg.com/post/using-celery-with-flask
#https://testdriven.io/blog/flask-and-celery/
#https://github.com/miguelgrinberg/flask-celery-example

#Sessions
#https://testdriven.io/blog/flask-server-side-sessions/

#https://flask.palletsprojects.com/en/2.0.x/patterns/celery/

def make_celery(app):
    celery = Celery(
        app.import_name,
        backend=app.config['CELERY_RESULT_BACKEND'],
        broker=app.config['CELERY_BROKER_URL']
    )
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery

cache = TTLCache(maxsize=100, ttl=7200)
app = Flask(__name__)
app.config.update(
    CELERY_BROKER_URL='redis://localhost:6379',
    CELERY_RESULT_BACKEND='redis://localhost:6379'
)

celery = make_celery(app)

# Alternative:
#celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
#celery.conf.update(app.config)

@celery.task(bind=True) #bind to get access to self.update_state of the celery worker
def getAnchorData(self, address):
    loadingMessages = ''
    # First, we query all historical rates. We need them for the plot and to calculate the yield for aUST transfers
    historicalRates = getHistoricalAUstRate()
    loadingMessages += 'Done: Historical Rates downladed! <br/>'
    self.update_state(state='PROGRESS', meta={'status': loadingMessages})

    error = ""
    # call anchor ...
    try:
        anchor = AnchorProtocolHandler(address, checkAllLogs=True)
        deposits,warnings = anchor.getAnchorTxs()
        currentRate = float(getCurrentAUstExchangeRate())
        totalYield = calculateYield(deposits, currentRate, historicalRates)
        loadingMessages += 'Done: Grabbed and analyzed all blockchain data! <br/>'
        self.update_state(state='PROGRESS', meta={'status': loadingMessages})
    except AssertionError:
        error = "Something went wrong with parsing the data. Please open a ticket: https://github.com/jensb89/anchor-earnings/issues"
        deposits = []
        totalYield = {'yield': 0, 'ustHoldings': 0, 'aUSTHoldings': 0}
        currentRate = 0
        warnings = ""
    except TooManyRequests:
        error = "Too many requests to https://fcd.terra.dev/. Try at a later time or raise a ticket if the error is shown all the time: https://github.com/jensb89/anchor-earnings/issues"
        deposits = []
        totalYield = {'yield': 0, 'ustHoldings': 0, 'aUSTHoldings': 0}
        currentRate = 0
        warnings = ""
    except BaseException:
        error = "Something went wrong. Please open a ticket:  https://github.com/jensb89/anchor-earnings/issues"
        deposits = []
        totalYield = {'yield': 0, 'ustHoldings': 0, 'aUSTHoldings': 0}
        currentRate = 0
        warnings = ""
    #todo: requests.exceptions.ConnectionError
    
    # Add UTC time in s
    minTime = datetime.datetime.now()
    for deposit in deposits:
        deposit["unixTimestamp"] = datetime.datetime.strptime(deposit["time"], "%Y-%m-%dT%H:%M:%SZ")
        minTime = min(minTime, deposit["unixTimestamp"])
        deposit["rate"] = deposit["Out"] / deposit["In"] if deposit["Out"] != 0 else getClosestHistoricalRate(historicalRates, deposit["time"])
    
    # Graph data
    histData = getHistData(deposits, historicalRates)
    loadingMessages += 'Done:Historical data calculated! <br/>'
    self.update_state(state='PROGRESS', meta={'status': loadingMessages})

    # get Eur rate
    rateEurUsd = getEurUsdRateFromTerraPriceOracle()
    self.update_state(state='PROGRESS', meta={'status': "Done:Eur rate queried!"})
    loadingMessages += 'Done:Eur rate queried! <br/>'
    self.update_state(state='PROGRESS', meta={'status': loadingMessages})

    return (deposits, address, totalYield, histData, rateEurUsd, error, warnings)

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
        wallet = request.form['taskidTest']
        print(wallet)
        return redirect(f"/address/{wallet}")

@app.route("/address/<address>", methods = ['POST', 'GET'])
def anchorErningsForAdress(address:str, checkAllLogs=False, id=None):

    # In the template we send a POST request with the task id when the task is finished. This way we can go back to the original page /addresss/address
    # via a POST request and distinguish if from the initial GET request and do not end up at address/<address>?id=taskId or address/<address>/taskId.
    # The template constantly calls status/taskId to get the current state
    if request.method == 'POST':
        # the form is value is called taskIdForm
        id = request.form['taskidForm']
        task = getAnchorData.AsyncResult(id)
        if task.state == "SUCCESS":
            # To prevent the dialaog "resend form data" and start a new call we sent a new GET request if the user reloads the page and at least 10min later
            # Otherwise the old data is relaoded (from the task result)
            if task.date_done and (task.date_done.replace(tzinfo=datetime.timezone.utc) < (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10))):
                return redirect(url_for('anchorErningsForAdress',address=address))
            # Retrieve the data from the celery worker
            (deposits, address, totalYield, histData, rateEurUsd, error, warnings) = task.get()
            # Finally render the template with the data
            return render_template('anchorOverview.html', deposits = deposits, address=address, y=totalYield, h=histData, eurRate = rateEurUsd, error=error, warnings=warnings )
        else:
            # this should not happen as we only send the POST request when the state is SUCCESS
            abort(400)
    #
    #id = request.args.get('id', id) #e.g. /address/terra1234?id=567
    #if id==None:

    else:
        # Start a new celery task and render the loadingPage
        task = getAnchorData.delay(address)
        info = {'status_url': url_for('taskstatus',task_id=task.id),'redirect_url':url_for('anchorErningsForAdress',address=address), 'id':task.id}
        return render_template("loadingPage.html", address=address, info=info)

@app.route('/status/<task_id>')
def taskstatus(task_id):
    task = getAnchorData.AsyncResult(task_id)
    if task.state == 'PENDING':
        response = {
            'state': task.state,
            'status': 'Pending...'
        }
    elif task.state != 'FAILURE' and task.state != "SUCCESS":
        response = {
            'state': task.state,
            'status': task.info.get('status', '')
        }
        #if 'result' in task.info:
        #    response['result'] = task.info['result']
    elif task.state == "SUCCESS":
        response = {
            'state': task.state,
            'status': 'Done...wait for redirect',
        }
    else:
        # something went wrong in the background job
        response = {
            'state': task.state,
            'status': str(task.info),  # this is the exception raised
        }
    return jsonify(response)

@app.route("/address/<address>/full")
def anchorErningsForAdressFull(address):
    return anchorErningsForAdress(address, checkAllLogs=True)

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
