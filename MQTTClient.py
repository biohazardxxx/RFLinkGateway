import logging
import multiprocessing
import time

import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish


class MQTTClient(multiprocessing.Process):
    def __init__(self, messageQ, commandQ, config):
        self.logger = logging.getLogger('RFLinkGW.MQTTClient')
        self.logger.info("Starting...")

        multiprocessing.Process.__init__(self)
        self.messageQ = messageQ
        self.commandQ = commandQ

        self.config = config
        self.auth = None
        self.host = config['mqtt_host']
        self.port = config['mqtt_port']

        self.mqttDataPrefix = config['mqtt_prefix']
        self._mqttConn = mqtt.Client(client_id='RFLinkGateway')
        if (config['mqtt_user'] is not None) or (len(config['mqtt_user'])==0):
            self.logger.info("Connection with credentials (user: %s).", config['mqtt_user'])
            self._mqttConn.username_pw_set(username=config['mqtt_user'], password=config['mqtt_password'])
            self.auth = {'username': config['mqtt_user'], 'password': config['mqtt_password']}
        self._mqttConn.connect(config['mqtt_host'], port=config['mqtt_port'], keepalive=120)

        self._mqttConn.on_connect = self._on_connect
        self._mqttConn.on_disconnect = self._on_disconnect
        self._mqttConn.on_publish = self._on_publish
        self._mqttConn.on_message = self._on_message

    def close(self):
        self.logger.info("Closing connection")
        self._mqttConn.disconnect()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.logger.info("Connected to broker. Return code: %s" % mqtt.connack_string(rc))
        else:
            self.logger.warning("An error occured on connect. Return code: %s " % mqtt.connack_string(rc))

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            self.logger.error("Unexpected disconnection. Return code: %s" % mqtt.connack_string(rc))
            self._mqttConn.reconnect()

    def _on_publish(self, client, userdata, mid):
        self.logger.debug("Message " + str(mid) + " published.")

    def _on_message(self, client, userdata, message):
        self.logger.debug("Message received: %s" % (message))

        data = message.topic.replace(self.mqttDataPrefix + "/", "").split("/")
        data_out = {
            'method': 'subscribe',
            'topic': message.topic,
            'family': data[0],
            'deviceId': data[1],
            'param': data[3],
            'payload': message.payload.decode('ascii'),
            'qos': 1
        }
        self.commandQ.put(data_out)

    def publish(self, task):
        topic = "%s/%s/%s/R/%s" % (self.mqttDataPrefix, task['family'], task['deviceId'], task['param'])
        try:
            self.logger.debug('Sending:%s' % (task))
            #self._mqttConn.publish(topic, payload=task['payload'])
            publish.single(topic, payload=task['payload'], hostname=self.host, auth=self.auth, port=self.port)
        except Exception as e:
            self.logger.error('Publish problem: %s' % (e))
            self.messageQ.put(task)

    def run(self):
        self._mqttConn.subscribe("%s/+/+/W/+" % self.mqttDataPrefix)
        while True:
            if not self.messageQ.empty():
                task = self.messageQ.get()
                if task['method'] == 'publish':
                    self.publish(task)
            else:
                time.sleep(0.01)
            self._mqttConn.loop()
