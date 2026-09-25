#!/bin/bash

envsubst < /home/logservice.conf.tmpl \
         > /home/logservice.conf
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    dpkg-reconfigure -f noninteractive tzdata

exec "$@"
