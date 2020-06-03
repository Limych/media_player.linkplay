# pylint: disable=W0511,C0412
"""
Support for LinkPlay based devices.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/media_player.linkplay/
"""

import binascii
import json
import upnpclient
import netdisco.ssdp
import logging
import os
import tempfile
import urllib.request
import xml.etree.ElementTree as ET

import homeassistant.helpers.config_validation as cv
import requests
import voluptuous as vol
from homeassistant.components.media_player import (MediaPlayerDevice)
from homeassistant.components.media_player.const import (
    DOMAIN, MEDIA_TYPE_MUSIC, SUPPORT_NEXT_TRACK, SUPPORT_PAUSE, SUPPORT_PLAY,
    SUPPORT_PLAY_MEDIA, SUPPORT_PREVIOUS_TRACK, SUPPORT_SEEK,
    SUPPORT_SELECT_SOUND_MODE, SUPPORT_SELECT_SOURCE, SUPPORT_SHUFFLE_SET,
    SUPPORT_TURN_OFF, SUPPORT_VOLUME_MUTE, SUPPORT_VOLUME_SET, SUPPORT_STOP)
from homeassistant.const import (
    ATTR_ENTITY_ID, CONF_HOST, CONF_NAME, STATE_PAUSED, STATE_PLAYING,
    STATE_UNKNOWN)
from homeassistant.util.dt import utcnow

from . import VERSION, ISSUE_URL, DATA_LINKPLAY

_LOGGER = logging.getLogger(__name__)

ATTR_MASTER = 'master_id'
ATTR_PRESET = 'preset'
ATTR_SLAVES = 'slave_ids'

CONF_DEVICE_NAME = 'device_name'
CONF_LASTFM_API_KEY = 'lastfm_api_key'
#
CONF_DEVICENAME_DEPRECATED = 'devicename'  # TODO: Remove this deprecated key in version 3.0

DEFAULT_NAME = 'LinkPlay device'

LASTFM_API_BASE = "http://ws.audioscrobbler.com/2.0/?method="

LINKPLAY_CONNECT_MULTIROOM_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_id,
    vol.Required(ATTR_MASTER): cv.entity_id
})
LINKPLAY_PRESET_BUTTON_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
    vol.Required(ATTR_PRESET): cv.positive_int
})
LINKPLAY_REMOVE_SLAVES_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_id,
    vol.Required(ATTR_SLAVES): cv.entity_ids
})

MAX_VOL = 100


def check_device_name_keys(conf):  # TODO: Remove this check in version 3.0
    """Ensure CONF_DEVICE_NAME or CONF_DEVICENAME_DEPRECATED are provided."""
    if sum(param in conf for param in
           [CONF_DEVICE_NAME, CONF_DEVICENAME_DEPRECATED]) != 1:
        raise vol.Invalid(CONF_DEVICE_NAME + ' key not provided')
    # if CONF_DEVICENAME_DEPRECATED in conf:    # TODO: Uncomment block in version 2.0
    #     _LOGGER.warning("Key %s is deprecated. Please replace it with key %s",
    #                     CONF_DEVICENAME_DEPRECATED, CONF_DEVICE_NAME)
    return conf


PLATFORM_SCHEMA = vol.All(cv.PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_DEVICE_NAME): cv.string,  # TODO: Mark required in version 3.0
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_LASTFM_API_KEY): cv.string,
    #
    vol.Optional(CONF_DEVICENAME_DEPRECATED): cv.string
}), check_device_name_keys)

SERVICE_CONNECT_MULTIROOM = 'linkplay_connect_multiroom'
SERVICE_PRESET_BUTTON = 'linkplay_preset_button'
SERVICE_REMOVE_SLAVES = 'linkplay_remove_slaves'

SERVICE_TO_METHOD = {
    SERVICE_CONNECT_MULTIROOM: {
        'method': 'connect_multiroom',
        'schema': LINKPLAY_CONNECT_MULTIROOM_SCHEMA},
    SERVICE_PRESET_BUTTON: {
        'method': 'preset_button',
        'schema': LINKPLAY_PRESET_BUTTON_SCHEMA},
    SERVICE_REMOVE_SLAVES: {
        'method': 'remove_slaves',
        'schema': LINKPLAY_REMOVE_SLAVES_SCHEMA}
}

SUPPORT_LINKPLAY = \
    SUPPORT_SELECT_SOURCE | SUPPORT_SELECT_SOUND_MODE | SUPPORT_SHUFFLE_SET | \
    SUPPORT_VOLUME_SET | SUPPORT_VOLUME_MUTE | \
    SUPPORT_NEXT_TRACK | SUPPORT_PAUSE | SUPPORT_STOP | SUPPORT_PLAY | \
    SUPPORT_TURN_OFF | SUPPORT_PREVIOUS_TRACK | SUPPORT_SEEK | SUPPORT_PLAY_MEDIA

SOUND_MODES = {'0': 'Normal', '1': 'Classic', '2': 'Pop', '3': 'Jazz',
               '4': 'Vocal'}
SOURCES = {'wifi': 'WiFi', 'line-in': 'Line-in', 'line-in2': 'Line-in2', 'bluetooth': 'Bluetooth',
           'optical': 'Optical', 'udisk': 'MicroSD'}
SOURCES_MAP = {'0': 'WiFi', '10': 'WiFi', '31': 'WiFi', '40': 'Line-in', '47': 'Line-in2',
               '41': 'Bluetooth', '43': 'Optical'}
UPNP_TIMEOUT = 5


# pylint: disable=W0613
def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the LinkPlay device."""
    # Print startup message
    _LOGGER.debug('Version %s', VERSION)
    _LOGGER.info('If you have any issues with this you need to open an issue '
                 'here: %s', ISSUE_URL)

    if DATA_LINKPLAY not in hass.data:
        hass.data[DATA_LINKPLAY] = {}

    def _service_handler(service):
        """Map services to method of Linkplay devices."""
        method = SERVICE_TO_METHOD.get(service.service)
        if not method:
            return

        params = {key: value for key, value in service.data.items()
                  if key != ATTR_ENTITY_ID}
        entity_ids = service.data.get(ATTR_ENTITY_ID)
        if entity_ids:
            target_players = [player for player in
                              hass.data[DATA_LINKPLAY].values()
                              if player.entity_id in entity_ids]
        else:
            target_players = None

        for player in target_players:
            getattr(player, method['method'])(**params)

    for service in SERVICE_TO_METHOD:
        schema = SERVICE_TO_METHOD[service]['schema']
        hass.services.register(
            DOMAIN, service, _service_handler, schema=schema)

    dev_name = config.get(CONF_DEVICE_NAME,
                          config.get(CONF_DEVICENAME_DEPRECATED))
    linkplay = LinkPlayDevice(config.get(CONF_HOST),
                              dev_name,
                              config.get(CONF_NAME),
                              config.get(CONF_LASTFM_API_KEY))

    add_entities([linkplay])
    hass.data[DATA_LINKPLAY][dev_name] = linkplay


# pylint: disable=R0902,R0904
class LinkPlayDevice(MediaPlayerDevice):
    """Representation of a LinkPlay device."""

    def __init__(self, host, devicename, name=None, lfm_api_key=None):
        """Initialize the LinkPlay device."""
        self._devicename = devicename
        if name is not None:
            self._name = name
        else:
            self._name = self._devicename
        self._host = host
        self._state = STATE_UNKNOWN
        self._volume = 0
        self._source = None
        self._source_list = SOURCES.copy()
        self._sound_mode = None
        self._muted = False
        self._seek_position = 0
        self._duration = 0
        self._position_updated_at = None
        self._shuffle = False
        self._media_album = None
        self._media_artist = None
        self._media_title = None
        self._lpapi = LinkPlayRestData(self._host)
        self._media_image_url = None
        self._media_uri = None
        self._first_update = True
        if lfm_api_key is not None:
            self._lfmapi = LastFMRestData(lfm_api_key)
        else:
            self._lfmapi = None
        self._upnp_device = None
        self._slave_mode = False
        self._slave_ip = None
        self._master = None
        self._wifi_channel = None
        self._ssid = None
        self._playing_spotify = None
        self._slave_list = None
        self._new_song = True

    @property
    def name(self):
        """Return the name of the device."""
        return self._name

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        return int(self._volume) / MAX_VOL

    @property
    def is_volume_muted(self):
        """Return boolean if volume is currently muted."""
        return bool(int(self._muted))

    @property
    def source(self):
        """Return the current input source."""
        return self._source

    @property
    def source_list(self):
        """Return the list of available input sources."""
        return sorted(list(self._source_list.values()))

    @property
    def sound_mode(self):
        """Return the current sound mode."""
        return self._sound_mode

    @property
    def sound_mode_list(self):
        """Return the available sound modes."""
        return sorted(list(SOUND_MODES.values()))

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        return SUPPORT_LINKPLAY

    @property
    def media_position(self):
        """Time in seconds of current seek position."""
        return self._seek_position

    @property
    def media_duration(self):
        """Time in seconds of current song duration."""
        return self._duration

    @property
    def media_position_updated_at(self):
        """When the seek position was last updated."""
        return self._position_updated_at

    @property
    def shuffle(self):
        """Return True if shuffle mode is enabled."""
        return self._shuffle

    @property
    def media_title(self):
        """Return title of the current track."""
        return self._media_title

    @property
    def media_artist(self):
        """Return name of the current track artist."""
        return self._media_artist

    @property
    def media_album_name(self):
        """Return name of the current track album."""
        return self._media_album

    @property
    def media_image_url(self):
        """Return name the image for the current track."""
        return self._media_image_url

    @property
    def media_content_type(self):
        """Content type of current playing media."""
        return MEDIA_TYPE_MUSIC

    @property
    def ssid(self):
        """SSID to use for multiroom configuration."""
        return self._ssid

    @property
    def wifi_channel(self):
        """Wifi channel to use for multiroom configuration."""
        return self._wifi_channel

    @property
    def slave_ip(self):
        """Ip used in multiroom configuration."""
        return self._slave_ip

    @property
    def lpapi(self):
        """Device API."""
        return self._lpapi

    def turn_on(self):
        """Turn the media player on."""
        _LOGGER.warning("This device cannot be turned on remotely.")

    def turn_off(self):
        """Turn off media player."""
        self._lpapi.call('GET', 'setShutdown:0')
        value = self._lpapi.data
        if value != "OK":
            _LOGGER.warning("Failed to power off the device. Got response: %s",
                            value)

    def set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        volume = str(round(volume * MAX_VOL))
        if not self._slave_mode:
            self._lpapi.call('GET', 'setPlayerCmd:vol:{0}'.format(str(volume)))
            value = self._lpapi.data
            if value == "OK":
                self._volume = volume
            else:
                _LOGGER.warning("Failed to set volume. Got response: %s",
                                value)
        else:
            self._master.lpapi.call('GET',
                                    'multiroom:SlaveVolume:{0}:{1}'.format(
                                        self._slave_ip, str(volume)))
            value = self._master.lpapi.data
            if value == "OK":
                self._volume = volume
            else:
                _LOGGER.warning("Failed to set volume. Got response: %s",
                                value)

    def mute_volume(self, mute):
        """Mute (true) or unmute (false) media player."""
        if not self._slave_mode:
            self._lpapi.call('GET',
                             'setPlayerCmd:mute:{0}'.format(str(int(mute))))
            value = self._lpapi.data
            if value == "OK":
                self._muted = mute
            else:
                _LOGGER.warning("Failed mute/unmute volume. Got response: %s",
                                value)
        else:
            self._master.lpapi.call('GET',
                                    'multiroom:SlaveMute:{0}:{1}'.format(
                                        self._slave_ip, str(int(mute))))
            value = self._master.lpapi.data
            if value == "OK":
                self._muted = mute
            else:
                _LOGGER.warning("Failed mute/unmute volume. Got response: %s",
                                value)

    def media_play(self):
        """Send play command."""
        if not self._slave_mode:
            self._lpapi.call('GET', 'setPlayerCmd:play')
            value = self._lpapi.data
            if value == "OK":
                self._state = STATE_PLAYING
                for slave in self._slave_list:
                    slave.set_state(STATE_PLAYING)
            else:
                _LOGGER.warning("Failed to start playback. Got response: %s",
                                value)
        else:
            self._master.media_play()

    def media_pause(self):
        """Send pause command."""
        if not self._slave_mode:
            self._lpapi.call('GET', 'setPlayerCmd:pause')
            value = self._lpapi.data
            if value == "OK":
                self._state = STATE_PAUSED
                for slave in self._slave_list:
                    slave.set_state(STATE_PAUSED)
            else:
                _LOGGER.warning("Failed to pause playback. Got response: %s",
                                value)
        else:
            self._master.media_pause()

    def media_stop(self):
        """Send stop command."""
        self.media_pause()

    def media_next_track(self):
        """Send next track command."""
        if not self._slave_mode:
            self._lpapi.call('GET', 'setPlayerCmd:next')
            value = self._lpapi.data
            if value != "OK":
                _LOGGER.warning("Failed skip to next track. Got response: %s",
                                value)
        else:
            self._master.media_next_track()

    def media_previous_track(self):
        """Send previous track command."""
        if not self._slave_mode:
            self._lpapi.call('GET', 'setPlayerCmd:prev')
            value = self._lpapi.data
            if value != "OK":
                _LOGGER.warning("Failed to skip to previous track."
                                " Got response: %s", value)
        else:
            self._master.media_previous_track()

    def media_seek(self, position):
        """Send media_seek command to media player."""
        if not self._slave_mode:
            self._lpapi.call('GET',
                             'setPlayerCmd:seek:{0}'.format(str(position)))
            value = self._lpapi.data
            if value != "OK":
                _LOGGER.warning("Failed to seek. Got response: %s",
                                value)
        else:
            self._master.media_seek(position)

    def clear_playlist(self):
        """Clear players playlist."""
        pass

    def play_media(self, media_type, media_id, **kwargs):
        """Play media from a URL or file."""
        if not self._slave_mode:
            if not media_type == MEDIA_TYPE_MUSIC:
                _LOGGER.error(
                    "Invalid media type %s. Only %s is supported",
                    media_type, MEDIA_TYPE_MUSIC)
                return
            self._lpapi.call('GET', 'setPlayerCmd:play:{0}'.format(media_id))
            value = self._lpapi.data
            if value != "OK":
                _LOGGER.warning("Failed to play media. Got response: %s",
                                value)
        else:
            self._master.play_media(media_type, media_id)

    def select_source(self, source):
        """Select input source."""
        if not self._slave_mode:
            if source == 'MicroSD':
                temp_source = 'udisk'
            else:
                temp_source = source.lower()
            self._lpapi.call('GET',
                             'setPlayerCmd:switchmode:{0}'.format(temp_source))
            value = self._lpapi.data
            if value == "OK":
                self._source = source
                for slave in self._slave_list:
                    slave.set_source(source)
            else:
                _LOGGER.warning("Failed to select source. Got response: %s",
                                value)
        else:
            self._master.select_source(source)

    def select_sound_mode(self, sound_mode):
        """Set Sound Mode for device."""
        if not self._slave_mode:
            mode = list(SOUND_MODES.keys())[list(
                SOUND_MODES.values()).index(sound_mode)]
            self._lpapi.call('GET', 'setPlayerCmd:equalizer:{0}'.format(mode))
            value = self._lpapi.data
            if value == "OK":
                self._sound_mode = sound_mode
                for slave in self._slave_list:
                    slave.set_sound_mode(sound_mode)
            else:
                _LOGGER.warning("Failed to set sound mode. Got response: %s",
                                value)
        else:
            self._master.select_sound_mode(sound_mode)

    def set_shuffle(self, shuffle):
        """Change the shuffle mode."""
        if not self._slave_mode:
            mode = '2' if shuffle else '0'
            self._lpapi.call('GET', 'setPlayerCmd:loopmode:{0}'.format(mode))
            value = self._lpapi.data
            if value != "OK":
                _LOGGER.warning("Failed to change shuffle mode. "
                                "Got response: %s", value)
        else:
            self._master.set_shuffle(shuffle)

    def preset_button(self, preset):
        """Simulate pressing a physical preset button."""
        if not self._slave_mode:
            self._lpapi.call('GET',
                             'IOSimuKeyIn:{0}'.format(str(preset).zfill(3)))
            value = self._lpapi.data
            if value != "OK":
                _LOGGER.warning("Failed to press preset button %s. "
                                "Got response: %s", preset, value)
        else:
            self._master.preset_button(preset)

    def connect_multiroom(self, master_id):
        """Add selected slaves to multiroom configuration."""
        for device in self.hass.data[DATA_LINKPLAY].values():
            if device.entity_id == master_id:
                cmd = "ConnectMasterAp:ssid={0}:ch={1}:auth=OPEN:".format(
                    device.ssid, device.wifi_channel) + \
                      "encry=NONE:pwd=:chext=0"
                self._lpapi.call('GET', cmd)
                value = self._lpapi.data
                if value == "OK":
                    self._slave_mode = True
                    self._master = device
                else:
                    _LOGGER.warning("Failed to connect multiroom. "
                                    "Got response: %s", value)

    def remove_slaves(self, slave_ids):
        """Remove selected slaves from multiroom configuration."""
        for slave_id in slave_ids:
            for device in self.hass.data[DATA_LINKPLAY].values():
                if device.entity_id == slave_id:
                    self._lpapi.call('GET',
                                     'multiroom:SlaveKickout:{0}'.format(
                                         device.slave_ip))
                    value = self._lpapi.data
                    if value == "OK":
                        device.set_slave_mode(False)
                        device.set_slave_ip(None)
                        device.set_master(None)
                    else:
                        _LOGGER.warning("Failed to remove slave %s. "
                                        "Got response: %s", slave_id, value)

    def set_master(self, master):
        """Set master device for multiroom configuration."""
        self._master = master

    def set_slave_mode(self, slave_mode):
        """Set current device as slave in a multiroom configuration."""
        self._slave_mode = slave_mode

    def set_media_title(self, title):
        """Set the media title property."""
        self._media_title = title

    def set_media_artist(self, artist):
        """Set the media artist property."""
        self._media_artist = artist

    def set_volume(self, volume):
        """Set the volume property."""
        self._volume = volume

    def set_muted(self, mute):
        """Set the muted property."""
        self._muted = mute

    def set_state(self, state):
        """Set the state property."""
        self._state = state

    def set_slave_ip(self, slave_ip):
        """Set the slave ip property."""
        self._slave_ip = slave_ip

    def set_seek_position(self, position):
        """Set the seek position property."""
        self._seek_position = position

    def set_duration(self, duration):
        """Set the duration property."""
        self._duration = duration

    def set_position_updated_at(self, time):
        """Set the position updated at property."""
        self._position_updated_at = time

    def set_source(self, source):
        """Set the source property."""
        self._source = source

    def set_sound_mode(self, mode):
        """Set the sound mode property."""
        self._sound_mode = mode

    def _is_playing_new_track(self, status):
        """Check if track is changed since last update."""
        if int(int(status['totlen']) / 1000) != self._duration:
            return True
        if status['totlen'] == '0':
            # Special case when listening to radio
            try:
                return bool(bytes.fromhex(
                    status['Title']).decode('utf-8') != self._media_title)
            except ValueError:
                return True
        return False

    def _update_via_upnp(self):
        """Update track info via UPNP."""
        import validators

        self._media_title = None
        self._media_album = None
        self._media_image_url = None

        if self._upnp_device is None:
            return

        media_info = self._upnp_device.AVTransport.GetMediaInfo(InstanceID=0)
        media_info = media_info.get('CurrentURIMetaData')

        if media_info is None:
            return

        xml_tree = ET.fromstring(media_info)

        xml_path = "{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}item/"
        title_xml_path = "{http://purl.org/dc/elements/1.1/}title"
        artist_xml_path = "{urn:schemas-upnp-org:metadata-1-0/upnp/}artist"
        album_xml_path = "{urn:schemas-upnp-org:metadata-1-0/upnp/}album"
        image_xml_path = "{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI"

        self._media_title = \
            xml_tree.find("{0}{1}".format(xml_path, title_xml_path)).text
        self._media_artist = \
            xml_tree.find("{0}{1}".format(xml_path, artist_xml_path)).text
        self._media_album = \
            xml_tree.find("{0}{1}".format(xml_path, album_xml_path)).text
        self._media_image_url = \
            xml_tree.find("{0}{1}".format(xml_path, image_xml_path)).text

        if not validators.url(self._media_image_url):
            self._media_image_url = None

    def _update_from_id3(self):
        """Update track info with eyed3."""
        import eyed3
        from urllib.error import URLError
        try:
            filename, _ = urllib.request.urlretrieve(self._media_uri)
            audiofile = eyed3.load(filename)
            self._media_title = audiofile.tag.title
            self._media_artist = audiofile.tag.artist
            self._media_album = audiofile.tag.album
            # Remove tempfile when done
            if filename.startswith(tempfile.gettempdir()):
                os.remove(filename)

        except (URLError, ValueError):
            self._media_title = None
            self._media_artist = None
            self._media_album = None

    def _get_lastfm_coverart(self):
        """Get cover art from last.fm."""
        self._lfmapi.call('GET',
                          'track.getInfo',
                          "artist={0}&track={1}".format(
                              self._media_artist,
                              self._media_title))
        lfmdata = json.loads(self._lfmapi.data)
        try:
            self._media_image_url = \
                lfmdata['track']['album']['image'][2]['#text']
        except (ValueError, KeyError):
            self._media_image_url = None

    def upnp_discover(self, timeout=5):
        devices = {}
        for entry in netdisco.ssdp.scan(timeout):
            if entry.location in devices:
                continue
            try:
                devices[entry.location] = upnpclient.Device(entry.location)
            except Exception as exc:
                _LOGGER.debug('Error \'%s\' for %s', exc, entry.location)
        return list(devices.values())

    # pylint: disable=R0912,R0915
    def update(self):
        """Get the latest player details from the device."""

        if self._slave_mode:
            return True

        if self._upnp_device is None:
            for entry in self.upnp_discover(UPNP_TIMEOUT):
                if entry.friendly_name == \
                        self._devicename:
                    self._upnp_device = upnpclient.Device(entry.location)
                    break

        self._lpapi.call('GET', 'getPlayerStatus')
        player_api_result = self._lpapi.data

        if player_api_result is None:
            _LOGGER.warning('Unable to connect to device')
            self._media_title = 'Unable to connect to device'
            return True

        try:
            player_status = json.loads(player_api_result)
        except ValueError:
            _LOGGER.warning("REST result could not be parsed as JSON")
            _LOGGER.debug("Erroneous JSON: %s", player_api_result)
            player_status = None

        if isinstance(player_status, dict):
            self._lpapi.call('GET', 'getStatus')
            device_api_result = self._lpapi.data
            if device_api_result is None:
                _LOGGER.warning('Unable to connect to device')
                self._media_title = 'Unable to connect to device'
                return True

            try:
                device_status = json.loads(device_api_result)
            except ValueError:
                _LOGGER.warning("REST result could not be parsed as JSON")
                _LOGGER.debug("Erroneous JSON: %s", device_api_result)
                device_status = None

            if isinstance(device_status, dict):
                self._wifi_channel = device_status['WifiChannel']
                self._ssid = \
                    binascii.hexlify(device_status['ssid'].encode('utf-8'))
                self._ssid = self._ssid.decode()

            # Update variables that changes during playback of a track.
            self._volume = player_status['vol']
            self._muted = player_status['mute']
            self._seek_position = int(int(player_status['curpos']) / 1000)
            self._position_updated_at = utcnow()
            try:
                self._media_uri = str(bytearray.fromhex(
                    player_status['iuri']).decode())
            except KeyError:
                self._media_uri = None
            self._state = {
                'stop': STATE_PAUSED,
                'play': STATE_PLAYING,
                'pause': STATE_PAUSED,
            }.get(player_status['status'], STATE_UNKNOWN)
            self._source = SOURCES_MAP.get(player_status['mode'],
                                           'WiFi')
            self._sound_mode = SOUND_MODES.get(player_status['eq'])
            self._shuffle = (player_status['loop'] == '2')
            self._playing_spotify = bool(player_status['mode'] == '31')

            self._new_song = self._is_playing_new_track(player_status)
            if self._playing_spotify or player_status['totlen'] == '0':
                self._update_via_upnp()

            elif self._media_uri is not None and self._new_song:
                self._update_from_id3()
                if self._lfmapi is not None and \
                        self._media_title is not None:
                    self._get_lastfm_coverart()
                else:
                    self._media_image_url = None

            self._duration = int(int(player_status['totlen']) / 1000)

        else:
            _LOGGER.warning("JSON result was not a dictionary")

        # Get multiroom slave information
        self._lpapi.call('GET', 'multiroom:getSlaveList')
        slave_list = self._lpapi.data

        try:
            slave_list = json.loads(slave_list)
        except ValueError:
            _LOGGER.warning("REST result could not be parsed as JSON")
            _LOGGER.debug("Erroneous JSON: %s", slave_list)
            slave_list = None

        self._slave_list = []
        if isinstance(slave_list, dict):
            if int(slave_list['slaves']) > 0:
                for slave in slave_list['slave_list']:
                    device = self.hass.data[DATA_LINKPLAY].get(slave['name'])
                    if device:
                        self._slave_list.append(device)
                        device.set_master(self)
                        device.set_slave_mode(True)
                        device.set_media_title("Slave mode")
                        device.set_media_artist(self.name)
                        device.set_volume(slave['volume'])
                        device.set_muted(slave['mute'])
                        device.set_state(self.state)
                        device.set_slave_ip(slave['ip'])
                        device.set_seek_position(self.media_position)
                        device.set_duration(self.media_duration)
                        device.set_position_updated_at(
                            self.media_position_updated_at)
                        device.set_source(self._source)
                        device.set_sound_mode(self._sound_mode)
        else:
            _LOGGER.warning("JSON result was not a dictionary")

        return True


# pylint: disable=R0903
class LinkPlayRestData:
    """Class for handling the data retrieval from the LinkPlay device."""

    def __init__(self, host):
        """Initialize the data object."""
        self.data = None
        self._request = None
        self._host = host

    def call(self, method, cmd):
        """Get the latest data from REST service."""
        self.data = None
        self._request = None
        resource = "http://{0}/httpapi.asp?command={1}".format(self._host, cmd)
        self._request = requests.Request(method, resource).prepare()

        _LOGGER.debug("Updating from %s", self._request.url)
        try:
            with requests.Session() as sess:
                response = sess.send(
                    self._request, timeout=2)
            self.data = response.text

        except requests.exceptions.RequestException as ex:
            _LOGGER.error("Error fetching data: %s from %s failed with %s",
                          self._request, self._request.url, ex)
            self.data = None


# pylint: disable=R0903
class LastFMRestData:
    """Class for handling the data retrieval from the LinkPlay device."""

    def __init__(self, api_key):
        """Initialize the data object."""
        self.data = None
        self._request = None
        self._api_key = api_key

    def call(self, method, cmd, params):
        """Get the latest data from REST service."""
        self.data = None
        self._request = None
        resource = "{0}{1}&{2}&api_key={3}&format=json".format(
            LASTFM_API_BASE, cmd, params, self._api_key)
        self._request = requests.Request(method, resource).prepare()
        _LOGGER.debug("Updating from %s", self._request.url)

        try:
            with requests.Session() as sess:
                response = sess.send(
                    self._request, timeout=10)
            self.data = response.text

        except requests.exceptions.RequestException as ex:
            _LOGGER.error("Error fetching data: %s from %s failed with %s",
                          self._request, self._request.url, ex)
            self.data = None
