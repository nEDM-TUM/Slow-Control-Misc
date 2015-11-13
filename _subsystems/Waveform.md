---
title: NMR Waveform
description: Module/daemon providing NMR waveform production
layout: basic
order: 50
---

## NMR Waveform

The `waveform` module provides a module that interfaces with the
[nEDM Interface]({{ site.url }}/nEDM-Interface), using a WebSocket
server to communicate with a waveform generator and produce NMR signals
that can be sent to coil systems.  The interface of the nEDM Interface is
described more [here]({{ site.url }}/nEDM-Interface/tutorial-user_special.html#waveform).

The `waveform` module code may be viewed
[here]({{ site.github.repository_url }}/tree/master/waveform).
`nedm1.waveform.plist` is included to show how one may run this as a daemon on
a Mac OS X machine.  This file should be edited, ensuring that all paths and
the following variables are correct:

{% highlight bash %}
DB_USER_NAME # username with write access to nedm%2Fwaveform
DB_PASSWORD # password
DB_URL # url to database, should generally be 'http://raid.nedm1'
SERVER_PORT # should generally be 9100
{% endhighlight %}

Starting the daemon (so that it will remain running):
{% highlight bash %}
cp nedm1.waveform.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/nedm1.waveform.plist
{% endhighlight %}

Stopping the daemon:
{% highlight bash %}
launchctl unload ~/Library/LaunchAgents/nedm1.waveform.plist
{% endhighlight %}

If code is updated, then simply kill the `python` process

{% highlight bash %}
kill `ps -ef | grep waveform_server | grep python | awk '{ print $2; }'`
{% endhighlight %}

