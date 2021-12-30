import requests
from string import Template
from time import sleep
from datetime import datetime, timedelta

def getAnchorDeposits(address = ""):
  endReached = False
  deposits = []
  reqItems = []
  offset = 0
  warnings = ""
  aUSTTransferWarningShown = False

  while not(endReached):
    response = requests.get('https://fcd.terra.dev/v1/txs?offset=' + str(offset) +'&limit=100&account=' + address)
    if response.status_code == 200:
        print('Success!')
    elif response.status_code == 404:
        print('Not Found.')
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

    # Sleep 10ms to prevent too many requests (427 error)
    sleep(0.01)

  if len(reqItems)==0:
    return deposits
  
  for page in reqItems:
    for item in page:
      for msg in item["tx"]["value"]["msg"]:
        # Anchor market maker contract found (deposit)
        if msg["type"]=="wasm/MsgExecuteContract" and msg["value"]["contract"] == "terra1sepfj7s0aeg5967uxnfk4thzlerrsktkpelm5s":

          # get fee
          assert(len(item["tx"]["value"]["fee"]["amount"]) == 1)
          feeItem = item["tx"]["value"]["fee"]["amount"][0]
          assert(feeItem["denom"]=="uusd")
          fee = feeItem["amount"]
          
          #Skip items without a log (failed transactions)
          if not "logs" in item:
            continue

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
                print("deposit")
                val = next(attribs)
                assert(val["key"] == "depositor" and val["value"] == address) #our wallet
                val = next(attribs)
                assert(val["key"] == "mint_amount")
                mintAmount = val["value"]
                print("Mint amount: %s" % mintAmount)
                val = next(attribs)
                assert(val["key"] == "deposit_amount")
                depositAmount = val["value"]
                print("Deposit amount: %s" % depositAmount)

                # Last checks
                val = next(attribs)
                assert(val["key"] == "contract_address" and val["value"] == "terra1hzh9vpxhsk8253se0vv5jj6etdvxu3nv8z07zu")
                val = next(attribs)
                assert(val["key"] == "action" and val["value"] == "mint")
                val = next(attribs)
                assert(val["key"] == "to" and val["value"] == address)
                val = next(attribs)
                assert(val["key"] == "amount" and val["value"] == mintAmount)

                # Save timestamp and data in a dictionary
                time = item["timestamp"]
                txId = item["txhash"]
                deposits.append({"In": float(mintAmount)/1E6, 
                                 "Out":float(depositAmount)/1E6, 
                                 "fee":float(fee)/1E6, 
                                 "feeUnit":"ust", 
                                 "time":time,
                                 "txId":txId})


        # Anchor aUST contract found (redemption)
        if msg["type"]=="wasm/MsgExecuteContract" and msg["value"]["contract"] == "terra1hzh9vpxhsk8253se0vv5jj6etdvxu3nv8z07zu":

          # get fee
          assert(len(item["tx"]["value"]["fee"]["amount"]) == 1)
          feeItem = item["tx"]["value"]["fee"]["amount"][0]
          assert(feeItem["denom"]=="uusd")
          fee = feeItem["amount"]

          # Find deposit and mint amount
          for log in item["logs"]:
            events = log["events"]
            for event in events:
              if event["type"] == "from_contract":
                #print(item["height"])
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

                  if val_from["value"] != address and val_to["value"] == address:
                    receive = True
                  elif val_from["value"] == address and val_to["value"] != address:
                    receive = False
                  
                  if receive == None:
                    continue

                  val = next(attribs)
                  assert(val["key"]=="amount")
                  aUstAmount = val["value"]

                  # Save timestamp and data in a dictionary
                  time = item["timestamp"]
                  txId = item["txhash"]
                  deposits.append({"In": float(aUstAmount)/1E6 if receive else -float(aUstAmount)/1E6, #todo:better naming of In and Out
                                  "Out":0,
                                  "fee":float(fee)/1E6, 
                                  "feeUnit":"ust", 
                                  "time":time,
                                  "txId":txId})
                  if not(aUSTTransferWarningShown):
                    warnings+="aUST transfer detected. aUST transfers are not fully supported yet: "\
                              "The aUST to UST rate is only estimated due to missing API endpoints."\
                              "The calculated yields could be erroneous (off by a day from the time of the aUST transfer)!"
                    aUSTTransferWarningShown = True
                  continue


                assert(val["key"] == "action" and val["value"] == "send")
                print("redeem aust")
                val = next(attribs)
                assert(val["key"] == "from" and val["value"] == address) #our wallet
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
                print(redeemAmount)
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
                deposits.append({"In": -float(burnAmount)/1E6, 
                                 "Out":-float(redeemAmount)/1E6, 
                                 "fee":float(fee)/1E6, 
                                 "feeUnit":"ust", 
                                 "time":time, #todo: check
                                 "txId":txId})
  return deposits, warnings


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