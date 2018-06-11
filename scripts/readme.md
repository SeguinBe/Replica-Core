# CINI uploads monitoring

This script should be run everyday in order to generate graphs on plot.ly about the state of the morphograph.

- First plotly must be installed on the machine : `pip install plotly`
- User should be configured : `python -c "import plotly; plotly.tools.set_credentials_file(username='my_username', api_key='my_api_key')"`
- Script should be executable : `sudo chmod 755 <script.py>`

- `crontab -e` in order to modify the cron jobs
- `0 10 * * * /home/seguin/Replica-Production/Replica-Core/scripts/generate_graph.py` for the script to be executed at 10am everyday

(inspired from [this webpage](http://moderndata.plot.ly/update-plotly-charts-with-cron-jobs-and-python/) )