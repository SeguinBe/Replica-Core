import sys
sys.path.append('..')
import core_server
from replica_core import model
import numpy as np
import pandas as pd
import plotly.plotly as py
import plotly.graph_objs as go
from datetime import datetime


links = model.VisualLink.nodes.filter(type='POSITIVE').all()
link_times = [l.added for l in links]

df = pd.DataFrame([(img.uid, l.added) for l in links for img in l.images], columns=['image', 'time'])
image_times = df.groupby('image').min().time


def cumsum_time_values(times):
    df = pd.DataFrame({'date': times, 'count': np.ones(len(times))}).set_index('date')
    df2 = df.resample('D').count()
    df2[df2.isnull()] = 0
    return df2.cumsum().reset_index()


df1 = cumsum_time_values(link_times)
df2 = cumsum_time_values(image_times)

data = [
    go.Scatter(
        x=df1['date'],
        y=df1['count'],
        name='Number of connections'
    ),
    go.Scatter(
        x=df2['date'],
        y=df2['count'],
        name='Number of unique artworks'
    )
]
layout = go.Layout(
    #title="Statistics about the graph annotations.<br>" +\
    title="<b>{}</b> connections between <b>{}</b> individual artworks<br>".format(len(link_times), len(image_times)) +\
    "<i>Graph generated on {}</i>".format(datetime.now().strftime('%Y-%m-%d %H:%M'))
)
fig = go.Figure(data=data, layout=layout)
# IPython notebook
#py.iplot(fig, filename='morphograph-stats')

py.plot(fig, filename='morphograph-stats', auto_open=False)
