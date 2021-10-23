import requests

def getAnchorDeposits(address = ""):
  response = requests.get('https://fcd.terra.dev/v1/txs?offset=0&limit=100&account=' + address)
  if response.status_code == 200:
      print('Success!')
  elif response.status_code == 404:
      print('Not Found.')
  else:
      raise Exception("Response failed!")
  
  deposits = []
  res = response.json()

  for item in res["txs"]:
    for msg in item["tx"]["value"]["msg"]:
      # Anchor contract found
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
              if val["key"] == "action" and val["value"] == "deposit_stable":
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
                time = item["timestamp"]
                deposits.append({"In": float(mintAmount)/1E6, "Out":float(depositAmount)/1E6, "fee":float(fee)/1E6, "feeUnit":"ust", "time":time})
              elif val["key"] == "action" and val["value"] == "redeem_stable":
                print("redeem")
                continue
              else:
                raise Exception("Unknown action")
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