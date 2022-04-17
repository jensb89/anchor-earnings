import requests
from string import Template
from time import sleep
from datetime import datetime, timedelta
import concurrent.futures
import random

class TooManyRequests(Exception):
    pass

class AnchorProtocolHandler(object):
  def __init__(self, address, checkAllLogs=False) -> None:
      self.address = address
      self.deposits = []
      self.warnings = ""
      self.aUSTTransferWarningShown = False
      self.checkAllLogs = checkAllLogs
      self.txs = []

  def getAnchorTxs(self):
    # Get all txs
    self.txs = self.queryTxs(self.address)
    self.handleTxs()
    return self.deposits, self.warnings
  
  def handleTxs(self):
    #with concurrent.futures.ProcessPoolExecutor() as executor:
    with concurrent.futures.ThreadPoolExecutor() as executor:
      #  futures = [executor.submit(self.checkEvent,item, event) for event in events]
      for page in self.txs:
        for item in page:
          msgs = item["tx"]["value"]["msg"]
          # Check the item message only for txs with less than 2 messages. Airdrops can have > 2k messages
          if len(msgs) < 2:
            for msg in item["tx"]["value"]["msg"]:
              executor.submit(self.handleItemMessage,item, msg)
          # For airdrops etc, we just check the logs and not the message, this way we don't check the logs multiple times 
          else: 
            executor.submit(self.handleAustInLogs,item)

  def handleItemMessage(self, item, msg):
    # Anchor market maker contract found (deposit)
    if msg["type"]=="wasm/MsgExecuteContract" and msg["value"]["contract"] == "terra1sepfj7s0aeg5967uxnfk4thzlerrsktkpelm5s":
      self.handleAnchorMarketContract(item)
    
    # Anchor aUST contract found (redemption)
    elif msg["type"]=="wasm/MsgExecuteContract" and msg["value"]["contract"] == "terra1hzh9vpxhsk8253se0vv5jj6etdvxu3nv8z07zu":
      self.handleAnchorAUSTContract(item)

    # Else search all logs for aUST ins/outs
    else:
      self.handleAustInLogs(item)

  def queryTxs(self, address=""):
    endReached = False
    reqItems = []
    offset = 0

    user_agent_list = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:77.0) Gecko/20100101 Firefox/77.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.97 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:77.0) Gecko/20100101 Firefox/77.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.97 Safari/537.36',
    ]

    while not(endReached):
      user_agent = random.choice(user_agent_list)
      response = requests.get('https://fcd.terra.dev/v1/txs?offset=' + str(offset) +'&limit=100&account=' + address, headers={'User-Agent': user_agent})
      if response.status_code == 200:
          print('Success!')
      elif response.status_code == 404:
          print('Not Found.')
      elif response.status_code == 429:
        raise TooManyRequests
      else:
          print("Error:" + str(response.status_code))
          #raise Exception("Response failed!") #todo: better error handling

      res = response.json()

      if not "txs" in res:
        endReached = True
        break
      
      if len(res['txs']) < 100:
        endReached = True
      
      if len(res['txs']) > 0:
        reqItems.append(res["txs"])
      
      if "next" in res:
        offset = res["next"]
      else:
        endReached = True

      # Sleep 1s to prevent too many requests (427 error)
      sleep(1)
    
    return reqItems

  def handleAnchorAUSTContract(self, item):
    # get fee
    assert(len(item["tx"]["value"]["fee"]["amount"]) == 1)
    feeItem = item["tx"]["value"]["fee"]["amount"][0]
    assert(feeItem["denom"]=="uusd")
    fee = feeItem["amount"]

    if not "logs" in item:
      return

    # Find deposit and mint amount
    for log in item["logs"]:
      events = log["events"]
      for event in events:
        if event["type"] == "from_contract":
          # Go through "from_contract"
          attribs = iter(event["attributes"])
          val = next(attribs)
          if( val["key"] == "contract_address" and val["value"] != "terra1hzh9vpxhsk8253se0vv5jj6etdvxu3nv8z07zu" ):
            #e.g. interacting with pylon contract (deposit via anchor market but send to pylon)
            continue
          val = next(attribs)

          #aUST transfer
          if(val["key"] == "action" and val["value"] == "transfer"): 
            receive = None
            val_from = next(attribs)
            val_to = next(attribs)
            assert(val_from["key"] == "from" and val_to["key"] == "to")

            if val_from["value"] != self.address and val_to["value"] == self.address:
              receive = True
            elif val_from["value"] == self.address and val_to["value"] != self.address:
              receive = False
            
            if receive == None:
              continue

            val = next(attribs)
            assert(val["key"]=="amount")
            aUstAmount = val["value"]

            # Save timestamp and data in a dictionary
            time = item["timestamp"]
            txId = item["txhash"]
            self.deposits.append({"In": float(aUstAmount)/1E6 if receive else -float(aUstAmount)/1E6, #todo:better naming of In and Out
                                  "Out":0,
                                  "fee":float(fee)/1E6, 
                                  "feeUnit":"ust", 
                                  "time":time,
                                  "txId":txId})
            if not(self.aUSTTransferWarningShown):
              self.warnings+="aUST transfer detected. aUST transfers are not fully supported yet: "\
                        "The aUST to UST rate is only estimated due to missing API endpoints."\
                        "The calculated yields could be erroneous (off by a day from the time of the aUST transfer)!"
              self.aUSTTransferWarningShownaUSTTransferWarningShown = True
            continue
          
          elif(val["key"] == "action" and val["value"] == "send"):
            #redeem aust
            assert(val["key"] == "action" and val["value"] == "send")
            val = next(attribs)
            assert(val["key"] == "from" and val["value"] == self.address) #our wallet
            val = next(attribs)
            assert(val["key"] == "to")
            if val["value"] != "terra1sepfj7s0aeg5967uxnfk4thzlerrsktkpelm5s":
              # if not the anchor contract, then we may interact with a mirror contract here (e.g. using aust as collateral
              # we skip these cases for now (todo: handle mirror contract interactions)
              continue
            val = next(attribs)
            assert(val["key"] == "amount")
            burnAmount = val["value"] #string
            val = next(attribs)
            assert(val["key"] == "contract_address" and val["value"] == "terra1sepfj7s0aeg5967uxnfk4thzlerrsktkpelm5s") # anchor contract
            val = next(attribs)
            assert(val["key"] == "action" and val["value"] == "redeem_stable") # anchor 
            val = next(attribs)
            assert(val["key"] == "burn_amount" and val["value"] == burnAmount) #todo: always like that?
            val = next(attribs)
            assert(val["key"] == "redeem_amount")
            redeemAmount = val["value"]
            val = next(attribs)
            assert(val["key"] == "contract_address" and val["value"] == "terra1hzh9vpxhsk8253se0vv5jj6etdvxu3nv8z07zu")
            val = next(attribs)
            assert(val["key"] == "action" and val["value"] == "burn")
            val = next(attribs)
            assert(val["key"] == "from" and val["value"] == "terra1sepfj7s0aeg5967uxnfk4thzlerrsktkpelm5s")
            val = next(attribs)
            assert(val["key"] == "amount" and val["value"] == burnAmount) #todo: always like that?             
            # Save timestamp and data in a dictionary
            time = item["timestamp"]
            txId = item["txhash"]
            self.deposits.append({"In": -float(burnAmount)/1E6, 
                                  "Out":-float(redeemAmount)/1E6, 
                                  "fee":float(fee)/1E6, 
                                  "feeUnit":"ust", 
                                  "time":time, #todo: check
                                  "txId":txId})
          else:
            # Check the logs instead
            self.handleAustInLogs(item)
            self.warnings+="Unknown aUST transaction with tx hash " + item["txhash"] + "\n"

  def handleAustInLogs(self, item):
    # No aUST contract execution found (no anchor deposit or redemption or aUST transfer). In that case we loop all transaction events 
    # to search for aUST amoutns received by other contracts (e.g. mirror contracts). See https://github.com/jensb89/anchor-earnings/issues/2
    if not "logs" in item or not self.checkAllLogs:
      return
    
    for log in item["logs"]:
      events = log["events"]
      with concurrent.futures.ThreadPoolExecutor() as executor:
        for event in events:
          executor.submit(self.checkEvent,item, event)
    
  def checkEvent(self, item, event):
    if event["type"] == "from_contract":
      attributes = event["attributes"]
      l = len(attributes)
      for index, attribute in enumerate(attributes):
        if attribute["key"] == "contract_address" and attribute["value"] == "terra1hzh9vpxhsk8253se0vv5jj6etdvxu3nv8z07zu":
          # check if aUST is transfered into our wallet
          if index + 4 < l:
            receive = None
            if (attributes[index+1]["key"] == "action" and attributes[index+1]["value"] == "transfer" and
                attributes[index+2]["key"] == "from" and
                attributes[index+3]["key"] == "to" and attributes[index+3]["value"] == self.address and
                attributes[index+4]["key"] == "amount"):

                aUstAmount = attributes[index+4]["value"]
                receive = True
          
            elif (attributes[index+1]["key"] == "action" and attributes[index+1]["value"] == "transfer" and
                  attributes[index+2]["key"] == "from" and attributes[index+2]["value"] == self.address and
                  attributes[index+3]["key"] == "to"  and
                  attributes[index+4]["key"] == "amount"):

                  aUstAmount = attributes[index+4]["value"]
                  receive = False
            
            if receive != None:    
                #Save timestamp and data in a dictionary
                time = item["timestamp"]
                txId = item["txhash"]
                self.deposits.append({"In": float(aUstAmount)/1E6 if receive else -float(aUstAmount)/1E6, #todo:better naming of In and Out
                                      "Out":0,
                                      "fee":float(0), #todo: fee 
                                      "feeUnit":"ust",
                                      "time":time,
                                      "txId":txId})
                if not(aUSTTransferWarningShown):
                  self.warnings+="aUST transfer detected. aUST transfers are not fully supported yet: "\
                            "The aUST to UST rate is only estimated due to missing API endpoints."\
                            "The calculated yields could be erroneous (off by a day from the time of the aUST transfer)!"
                  aUSTTransferWarningShown = True
                continue
  
  def handleAnchorMarketContract(self, item):
    # get fee
    assert(len(item["tx"]["value"]["fee"]["amount"]) == 1)
    feeItem = item["tx"]["value"]["fee"]["amount"][0]
    assert(feeItem["denom"]=="uusd")
    fee = feeItem["amount"]
    
    #Skip items without a log (failed transactions)
    if not "logs" in item:
      return

    # Find deposit and mint amount
    for log in item["logs"]:
      events = log["events"]
      for event in events:
        if event["type"] == "from_contract":
          # Go through "from_contract"
          attribs = iter(event["attributes"])
          val = next(attribs)
          if(val["key"] == "contract_address" and val["value"] != "terra1sepfj7s0aeg5967uxnfk4thzlerrsktkpelm5s"):
            # skip all non anchor contracts
            continue
          val = next(attribs)
          if(val["key"] == "action" and val["value"] != "deposit_stable"):
            #skip all non-deposits: borrow_stable, repay_stable, claim_rewards, ... 
            # https://docs.anchorprotocol.com/smart-contracts/money-market/market
            continue
          assert(val["key"] == "action" and val["value"] == "deposit_stable")
          val = next(attribs)
          assert(val["key"] == "depositor" and val["value"] == self.address) #our wallet
          val = next(attribs)
          assert(val["key"] == "mint_amount")
          mintAmount = val["value"]
          val = next(attribs)
          assert(val["key"] == "deposit_amount")
          depositAmount = val["value"]

          # Last checks
          val = next(attribs)
          assert(val["key"] == "contract_address" and val["value"] == "terra1hzh9vpxhsk8253se0vv5jj6etdvxu3nv8z07zu")
          val = next(attribs)
          assert(val["key"] == "action" and val["value"] == "mint")
          val = next(attribs)
          assert(val["key"] == "to" and val["value"] == self.address)
          val = next(attribs)
          assert(val["key"] == "amount" and val["value"] == mintAmount)

          # Save timestamp and data in a dictionary
          time = item["timestamp"]
          txId = item["txhash"]
          self.deposits.append({"In": float(mintAmount)/1E6, 
                                "Out":float(depositAmount)/1E6, 
                                "fee":float(fee)/1E6, 
                                "feeUnit":"ust", 
                                "time":time,
                                "txId":txId})


def calculateYield(deposits, currentaUstRate, historicalRates):
    aUstAmount= 0
    rates = []
    yields = []
    for d in deposits:
        r = d["Out"]/d["In"]
        aUstAmount += d["In"]
        # Yield
        if d["Out"]!=0:
          y = (currentaUstRate - r) * d["In"] 
        else:
          y = (currentaUstRate - getClosestHistoricalRate(historicalRates, d["time"])) * d["In"]  #aUST transfers
          #note: these are not exact numbers yet, just an estimate of the closest rate that we have for the given date 
        rates.append(r)
        yields.append(y)
    
    out = {'yield': sum(yields), 'ustHoldings': aUstAmount * currentaUstRate, 'aUSTHoldings':aUstAmount}
    return out

def getClosestHistoricalRate(historicalRates, date):
    if len(historicalRates) == 0:
      return 0 #will lead to too high yield. todo: check historical rates request at the beginning. It should not be empty here!
      
    searchDate = datetime.strptime(date, "%Y-%m-%dT%H:%M:%SZ")
    def minimizeFunc(x):
       d =  x[0]
       delta =  d - searchDate if d > searchDate else timedelta.max
       return delta
    return min(historicalRates, key = minimizeFunc)[1]

def getCurrentAUstExchangeRate():
    ret = requests.get("https://lcd.terra.dev/wasm/contracts/terra1sepfj7s0aeg5967uxnfk4thzlerrsktkpelm5s/store?query_msg={\"epoch_state\":{}}")
    return ret.json()["result"]["exchange_rate"]

def getCurrentAUstBalance(accountAddress=""):
    query =  Template("""query {
            WasmContractsContractAddressStore(
                ContractAddress : "terra1hzh9vpxhsk8253se0vv5jj6etdvxu3nv8z07zu"
                QueryMsg: $msg
            ) {
            Height
            Result
            __typename
          }
        }
        """)

    message = '''"{\\"balance\\":{\\"address\\":\\"{0}\\"}}"'''.replace('{0}', accountAddress)     
    query = query.substitute(msg=message)

    # Execute Graph QL query
    request = requests.post('https://mantle.terra.dev', json={'query': query})
    if request.status_code == 200:
        return request.json()["data"]["WasmContractsContractAddressStore"]["Result"]["balance"]
    else:
        raise Exception("Graphl QL Query failed to run by returning code of {}. {}".format(request.status_code, query))