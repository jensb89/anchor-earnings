# Anchor earnings

Flask website that shows all deposits + earnings from Anchor protocol.

Try it out by going to https://anchor-earnings.herokuapp.com/
or directly to https://anchor-earnings.herokuapp.com/address/TERRA-ADDRESS (replace TERRA-ADDRESS with your address).

# Screenshots
![](https://github.com/jensb89/anchor-earnings/raw/imgs/MacScreenShotEarnings.png)
<img src="https://github.com/jensb89/anchor-earnings/raw/imgs/iphoneScreenShotMain.PNG" width="400" />
<img src="https://github.com/jensb89/anchor-earnings/raw/imgs/iphoneScreenShotEarnings.PNG" width="400" />

# Development

1. Install Redis Server and start with "redis-server"
2. Create a virtual environment
3. Install requirements ("pip install -r requirements.txt")
4. Start Celery worker with "celery -A app.celery worker --loglevel=info"
5. Run the webserver locally in debug mode with "export FLASK_DEBUG=1 && flask run".

To be clear: This project was created in one weekend and is in a super early stage. 
Yet, deposits and redemptions at the Anchor protocol as well as a plot with the gains over time are shown.

The code can still be massively improved. If you want to improve it, feel free to submit a pull request.

Todos:
 * Use client side download of tx data in order to avoid too many requests when a lot of people are using the site at the same time
 * Better error handling needed (catch of exceptions, error code of responses, showing meaningful warnings in the HTML page etc.)
 * Handle interactions with Mirror contracts (using aUST as collateral)
 * Check redemptions calculation (yields affected by redeeming aUST to UST)
 * Unit tests

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.
Info: All merged commits on "main" automatically trigger a rebuild of the app in Heroku (git push -u origin main).

## Donate

To keep me motivated and support this little project, feel free to donate to the following Terra address: terra1udrz5xmtj4vg7uwu653dpk54sleqfwcrdnpccy

## License
[MIT](https://choosealicense.com/licenses/mit/)