import requests
from string import Template

def getAnchorDeposits(address = ""):
  endReached = False
  deposits = []
  reqItems = []
  offset = 0
  while not(endReached):
    response = requests.get('https://fcd.terra.dev/v1/txs?offset=' + str(offset) +'&limit=100&account=' + address)
    if response.status_code == 200:
        print('Success!')
    elif response.status_code == 404:
        print('Not Found.')
    else:
        print(response.status_code)
        #raise Exception("Response failed!") #todo: better error handling
    
    res = response.json()

    if not "txs" in res:
      endReached = True
      break
    
    if len(res['txs']) < 100:
      endReached = True
    
    if len(res['txs']) > 0:
      reqItems.append(res["txs"])
    
    offset = offset + 100

  if len(reqItems)==0:
    return deposits

  for item in reqItems[0]:
    for msg in item["tx"]["value"]["msg"]:
      # Anchor contract found (deposit)
      if msg["type"]=="wasm/MsgExecuteContract" and msg["value"]["contract"] == "terra1sepfj7s0aeg5967uxnfk4thzlerrsktkpelm5s":

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
              # Go through "from_contract"
              attribs = iter(event["attributes"])
              val = next(attribs)
              assert(val["key"] == "contract_address" and val["value"] == "terra1sepfj7s0aeg5967uxnfk4thzlerrsktkpelm5s")
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
              deposits.append({"In": float(mintAmount)/1E6, "Out":float(depositAmount)/1E6, "fee":float(fee)/1E6, "feeUnit":"ust", "time":time})


      # Anchor contract found (redemption)
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
              assert(val["key"] == "contract_address" and val["value"] == "terra1hzh9vpxhsk8253se0vv5jj6etdvxu3nv8z07zu")
              val = next(attribs)
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
              deposits.append({"In": -float(burnAmount)/1E6, "Out":-float(redeemAmount)/1E6, "fee":float(fee)/1E6, "feeUnit":"ust", "time":time}) #todo: check
  return deposits


def calculateYield(deposits, currentaUstRate):
    aUstAmount= 0
    rates = []
    yields = []
    for d in deposits:
        r = d["Out"]/d["In"]
        aUstAmount += d["In"]
        # Yield
        y = (currentaUstRate - r) * d["In"]
        rates.append(r)
        yields.append(y)
    
    out = {'yield': sum(yields), 'ustHoldings': aUstAmount * currentaUstRate}
    return out

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