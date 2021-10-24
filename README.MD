# Anchor earnings

Flask website that shows all deposits + earnings from Anchor protocol.

Try it out by going to https://anchor-earnings.herokuapp.com/address/TERRA-ADDRESS (replace TERRA-ADDRESS with your address)

Run locally in debug mode with "export FLASK_DEBUG=1 && flask run"

# Screenshots
coming soon

# Development
To be clear: This project was created in one weekend and is in a super early stage. 
Yet, deposits and redemptions at the Anchor protocol as well as a plot with the gains over time are shown.

The code can still be massively improved. If you want to improve it, feel free to submit a pull request.

Todos:
 * Better error handling needed (catch of exceptions, error code of responses, showing meaningful warnings in the HTML page etc.)
 * Handle transfers of aUST tokens
 * Handle interactions with Mirror contracts (using aUST as collateral)
 * Check redemptions calculation (yields affected by redeeming aUST to UST)
 * Unit tests

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.
Info: All merged commits on "main" automatically trigger a rebuild of the app in Heroku (git push -u origin main).

## License
[MIT](https://choosealicense.com/licenses/mit/)