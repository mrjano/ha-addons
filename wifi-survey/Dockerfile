ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache iw iproute2-minimal python3 py3-paho-mqtt

COPY run.sh /run.sh
COPY survey.py /survey.py
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
