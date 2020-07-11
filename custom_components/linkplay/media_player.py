"""
Support for LinkPlay based devices.

For more details about this platform, please refer to the documentation at
https://github.com/nagyrobi/home-assistant-custom-components-linkplay
"""

import binascii
import json
from json import loads, dumps
import upnpclient
import netdisco.ssdp
import logging
import os
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import time
from datetime import timedelta
import socket
import homeassistant.helpers.config_validation as cv
import requests
import voluptuous as vol
from homeassistant.components.media_player import (DEVICE_CLASS_SPEAKER, MediaPlayerEntity)
from homeassistant.components.media_player.const import (
    DOMAIN, MEDIA_TYPE_MUSIC, SUPPORT_NEXT_TRACK, SUPPORT_PAUSE, SUPPORT_PLAY,
    SUPPORT_PLAY_MEDIA, SUPPORT_PREVIOUS_TRACK, SUPPORT_SEEK,
    SUPPORT_SELECT_SOUND_MODE, SUPPORT_SELECT_SOURCE, SUPPORT_SHUFFLE_SET,
    SUPPORT_VOLUME_MUTE, SUPPORT_VOLUME_SET, SUPPORT_STOP)  # SUPPORT_TURN_OFF, 
from homeassistant.const import (
    ATTR_ENTITY_ID, ATTR_DEVICE_CLASS, CONF_HOST, CONF_NAME, STATE_PAUSED, STATE_PLAYING, STATE_ON, STATE_IDLE, STATE_UNKNOWN, STATE_UNAVAILABLE)
from homeassistant.util.dt import utcnow
from homeassistant.util import Throttle

from . import VERSION, ISSUE_URL, DOMAIN, ATTR_MASTER

_LOGGER = logging.getLogger(__name__)

#ATTR_MASTER = 'master'
ATTR_SLAVE = 'slave'
ATTR_LINKPLAY_GROUP = 'linkplay_group'
ATTR_FWVER = 'firmware'

PARALLEL_UPDATES = 0

ICON_DEFAULT = 'mdi:speaker'
ICON_PLAYING = 'mdi:speaker-wireless'
ICON_MUTED = 'mdi:speaker-off'
ICON_MULTIROOM = 'mdi:speaker-multiple'
ICON_BLUETOOTH = 'mdi:speaker-bluetooth'
ICON_DLNA = 'mdi:cast-audio'

CONF_NAME = 'name'
CONF_LASTFM_API_KEY = 'lastfm_api_key'
CONF_SOURCES = 'sources'
CONF_ICECAST_METADATA = 'icecast_metadata'
CONF_MULTIROOM_WIFIDIRECT = 'multiroom_wifidirect'

LASTFM_API_BASE = 'http://ws.audioscrobbler.com/2.0/?method='
MAX_VOL = 100
UNAVAIL_MAX = 10
FW_MROOM_RTR_MIN = '4.2.8020'
UPNP_TIMEOUT = 3
TCPPORT = 8899
ICE_THROTTLE = timedelta(seconds=60)
UNA_THROTTLE = timedelta(seconds=60)

DEFAULT_ICECAST_UPDATE = 'StationName'
#DEFAULT_MULTIROOM_MSG = 'Sound from'
DEFAULT_MULTIROOM_WIFIDIRECT = False

PLATFORM_SCHEMA = vol.All(cv.PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_NAME): cv.string,
    vol.Optional(CONF_ICECAST_METADATA, default=DEFAULT_ICECAST_UPDATE): vol.In(['Off', 'StationName', 'StationNameSongTitle']),
    vol.Optional(CONF_MULTIROOM_WIFIDIRECT, default=DEFAULT_MULTIROOM_WIFIDIRECT): cv.boolean,
    vol.Optional(CONF_SOURCES): cv.ensure_list,
    vol.Optional(CONF_LASTFM_API_KEY): cv.string,
}))

SUPPORT_LINKPLAY = \
    SUPPORT_SELECT_SOURCE | SUPPORT_SELECT_SOUND_MODE | SUPPORT_SHUFFLE_SET | \
    SUPPORT_VOLUME_SET | SUPPORT_VOLUME_MUTE | \
    SUPPORT_NEXT_TRACK | SUPPORT_PAUSE | SUPPORT_STOP | SUPPORT_PLAY | \
    SUPPORT_PREVIOUS_TRACK | SUPPORT_SEEK | SUPPORT_PLAY_MEDIA  # SUPPORT_TURN_OFF | 

SOUND_MODES = {'0': 'Normal', '1': 'Classic', '2': 'Pop', '3': 'Jazz', '4': 'Vocal'}

SOURCES = {'wifi': 'WiFi', 
           'line-in': 'Line-in', 
           'line-in2': 'Line-in2', 
           'bluetooth': 'Bluetooth', 
           'optical': 'Optical', 
           'rca': 'RCA', 
           'co-axial': 'S-PDIF', 
           'tfcard': 'SD',
           'hdmi': 'HDMI',
           'xlr': 'XLR', 
           'fm': 'FM', 
           'cd': 'CD', 
           'udisk': 'USB'}

SOURCES_MAP = {'0': 'Idle', 
               '1': 'Airplay', 
               '2': 'DLNA',
               '3': 'QPlay',
               '10': 'WiFi', 
               '11': 'USB', 
               '16': 'SD', 
               '20': 'API', 
               '21': 'USB', 
               '30': 'Alarm', 
               '31': 'Spotify', 
               '40': 'Line-in', 
               '41': 'Bluetooth', 
               '43': 'Optical',
               '44': 'RCA',
               '45': 'S-PDIF',
               '46': 'FM',
               '47': 'Line-in2', 
               '48': 'XLR',
               '49': 'HDMI',
               '50': 'CD/Mirror',
               '52': 'TFcard'}

class LinkPlayData:
    """Storage class for platform global data."""
    def __init__(self):
        """Initialize the data."""
        self.entities = []

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the LinkPlay device."""
    # Print startup message
    _LOGGER.debug('Version %s', VERSION)
    _LOGGER.info('If you have any issues with this you need to open an issue here: %s', ISSUE_URL)

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = LinkPlayData()  # {}
        
    resource = "http://{0}/httpapi.asp?command=getStatus".format(config.get(CONF_HOST))
    rqst = requests.Request("GET", resource).prepare()
    
    _LOGGER.debug("Getting DeviceName from %s", config.get(CONF_HOST))
    try:
        with requests.Session() as sess:
            response = sess.send(rqst, timeout=2)
        resp_data = response.text
    except requests.exceptions.RequestException as ex:
        # _LOGGER.warning("Error fetching data: %s from %s failed with %s", self._request, self._request.url, ex)
        resp_data = None
        unavailable = True

    if resp_data is not None:
        try:
            resp_json = json.loads(resp_data)
        except ValueError:
            # _LOGGER.warning("REST result could not be parsed as JSON")
            _LOGGER.debug("Erroneous JSON: %s", device_api_result)
            resp_json = None
            unavailable = True

        if resp_json is not None and isinstance(resp_json, dict):
            name = resp_json['DeviceName']
            fw_ver = resp_json['firmware']
            unique_id = resp_json['uuid']
            model = resp_json['hardware']
            mac_address = resp_json['STA_MAC']
            manufacturer = resp_json['project']
            preset_key = int(resp_json['preset_key'])
            unavailable = False
            _LOGGER.info("Device Name detected: %s, firmware: %s", name, fw_ver)
        else:
            name = config.get(CONF_NAME)
            unavailable = True
    else:
        name = config.get(CONF_NAME)
        unavailable = True
        
    if unavailable:
        fw_ver = None
        unique_id = None
        model = None
        mac_address = None
        manufacturer = None
        preset_key = None
        _LOGGER.info("Device unavailable, name from config: %s", name)

    linkplay = LinkPlayDevice(config.get(CONF_HOST),
                              name,
                              name,
                              config.get(CONF_SOURCES),
                              config.get(CONF_ICECAST_METADATA),
                              config.get(CONF_MULTIROOM_WIFIDIRECT),
                              unavailable,
                              fw_ver,
                              unique_id,
                              model,
                              mac_address,
                              manufacturer,
                              preset_key,
                              config.get(CONF_LASTFM_API_KEY))
    
    add_entities([linkplay])

class LinkPlayDevice(MediaPlayerEntity):
    """Representation of a LinkPlay device."""

    def __init__(self, 
                 host, 
                 name,
                 dev_name,
                 sources, 
                 icecast_meta, 
                 multiroom_wifidierct, 
                 unavailable,
                 fw_ver, 
                 unique_id,
                 model,
                 mac_address,
                 manufacturer,
                 preset_key, 
                 lfm_api_key=None
                 ):
        """Initialize the LinkPlay device."""
        self._fw_ver = fw_ver
        self._unique_id = unique_id
        self._model = model
        self._mac_address = mac_address
        self._manufacturer = manufacturer
        self._preset_key = preset_key
        self._name = name #dev_name
        self._devicename = name
        self._host = host
        self._icon = ICON_DEFAULT
        self._state = STATE_UNAVAILABLE  #STATE_UNKNOWN
        self._volume = 0
        self._fadevol = True
        self._source = None
        self._prev_source = None
        if sources is not None:
            self._source_list = loads(dumps(sources).strip('[]'))
        else:
            self._source_list = SOURCES.copy()
        self._sound_mode = None
        self._muted = False
        self._seek_position = 0
        self._duration = 0
        self._position_updated_at = None
        self._shuffle = False
        self._media_album = None
        self._media_artist = None
        self._media_prev_artist = None
        self._media_title = None
        self._media_prev_title = None
        self._lpapi = LinkPlayRestData(self._host)
        self._tcpapi = LinkPlayTcpUartData(self._host)
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
        self._is_master = False
        self._wifi_channel = None
        self._ssid = None
        self._playing_spotify = False
        self._playing_stream = False
        self._slave_list = None
        self._multiroom_wifidierct = multiroom_wifidierct
        self._multiroom_group = []
        self._wait_for_fade = False
        self._new_song = True
        self._skip_throttle = False
        self._unav_throttle = unavailable
        self._counter_unavail = 0
        self._icecast_name = None
        self._icecast_meta = icecast_meta
        self._snap_source = None
        self._snap_state = STATE_UNKNOWN
        self._snap_volume = 0
        

        def fwvercheck(v):
           filled = []
           for point in v.split("."):
              filled.append(point.zfill(8))
           return tuple(filled)
        
        if not self._multiroom_wifidierct and self._fw_ver:
            if fwvercheck(self._fw_ver) < fwvercheck(FW_MROOM_RTR_MIN):
                self._multiroom_wifidierct = True

    async def async_added_to_hass(self):
        """Record entity."""
        self.hass.data[DOMAIN].entities.append(self)


    @property
    def name(self):
        """Return the name of the device."""
        if self._slave_mode:
            for dev in self._multiroom_group:
                for device in self.hass.data[DOMAIN].entities:
                    if device._is_master:
                        return self._name + ' [' + device._name + ']'
        else:
            return self._name

    @property
    def icon(self):
        """Return the icon of the device."""
        if self._muted or self._state == STATE_PAUSED or self._state == STATE_UNAVAILABLE:
            return ICON_MUTED
        
        if self._slave_mode or self._is_master:
            return ICON_MULTIROOM
            
        if self._source == "Bluetooth":
            return ICON_BLUETOOTH
            
        if self._source == "DLNA" or self._source == "Airplay":
            return ICON_DLNA
            
        if self._state == STATE_PLAYING:
            return ICON_PLAYING
            
        return ICON_DEFAULT

    @property
    def fw_ver(self):
        """Return the firmware version number of the device."""
        return self._fw_ver

#    @property
#    def unique_id(self):
#        """Return a unique ID."""
#        return self._unique_id

#    @property
#    def device_info(self):
#        """Return information about the device."""
#        return {
#            "identifiers": {(DOMAIN, self._unique_id)},
#            "name": self._name,
#            "model": self._model,
#            "sw_version": self._fw_ver,
#            "manufacturer": self._manufacturer,
#        }

        
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
        return self._muted

    @property
    def source(self):
        """Return the current input source."""
        return self._source

    @property
    def source_list(self):
        """Return the list of available input sources. If only one source exists, don't show it, as it's one and only one. WiFi shouldn't be listed."""
        if len(self._source_list) > 1:
            source_list = self._source_list.copy()
            if 'wifi' in source_list:
                del source_list['wifi']

            return list(source_list.values())
        else:
            return None

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
    def slave(self):
        """Return true if it is a slave."""
        return self._slave_mode

    @property
    def master(self):
        """master's entity id used in multiroom configuration."""
        return self._master

    @property
    def is_master(self):
        """Return true if it is a master."""
        return self._is_master
        
    @property
    def device_state_attributes(self):
        """List members in group and set master and slave state."""
        attributes = {}
        if self._multiroom_group is not None:
            attributes = {ATTR_LINKPLAY_GROUP: self._multiroom_group}

        attributes[ATTR_MASTER] = self._is_master
        attributes[ATTR_SLAVE] = self._slave_mode
        attributes[ATTR_FWVER] = self._fw_ver
        attributes[ATTR_DEVICE_CLASS] = DEVICE_CLASS_SPEAKER

        return attributes

    @property
    def host(self):
        """Self ip."""
        return self._host

    @property
    def lpapi(self):
        """Device API."""
        return self._lpapi

    def set_volume_level(self, volume):
        """Set volume level, input range 0..1, linkplay device 0..100."""
        volume = str(round(volume * MAX_VOL))
        if not self._slave_mode:

            if self._fadevol:
                voldiff = int(self._volume) - int(volume)
                steps = 1
                if voldiff < 33:
                    steps = 2
                elif voldiff >= 33 and voldiff < 66:
                    steps = 4
                elif voldiff > 66:
                    steps = 6
                volstep = int(round(voldiff / steps))
                voltemp = int(self._volume)
#                self._wait_for_fade = True  # set delay in update routine for the fade to finish
                for v in (range(0, steps - 1)):
                    voltemp = voltemp - volstep
                    self._lpapi.call('GET', 'setPlayerCmd:vol:{0}'.format(str(voltemp)))
                    time.sleep(0.6 / steps)
                                       
            self._lpapi.call('GET', 'setPlayerCmd:vol:{0}'.format(str(volume)))
            value = self._lpapi.data

            if value == "OK":
                self._volume = volume
            else:
                _LOGGER.warning("Failed to set volume. Got response: %s", value)
        else:
            self._master.lpapi.call('GET',
                                    'multiroom:SlaveVolume:{0}:{1}'.format(
                                        self._slave_ip, str(volume)))
            value = self._master.lpapi.data
            if value == "OK":
                self._volume = volume
            else:
                _LOGGER.warning("Failed to set volume. Got response: %s", value)

    def mute_volume(self, mute):
        """Mute (true) or unmute (false) media player."""
       
        if not self._slave_mode:
            self._lpapi.call('GET',
                             'setPlayerCmd:mute:{0}'.format(str(int(mute))))
            value = self._lpapi.data
            if value == "OK":
                self._muted = bool(int(mute))
            else:
                _LOGGER.warning("Failed mute/unmute volume. Got response: %s", value)
        else:
            self._master.lpapi.call('GET',
                                    'multiroom:SlaveMute:{0}:{1}'.format(
                                        self._slave_ip, str(int(mute))))
            value = self._master.lpapi.data
            if value == "OK":
                self._muted = bool(int(mute))
            else:
                _LOGGER.warning("Failed mute/unmute volume. Got response: %s", value)

    def media_play(self):
        """Send play command."""
        if not self._slave_mode:
            if self._prev_source != None:
                temp_source = next((k for k in self._source_list if self._source_list[k] == self._prev_source), None)
                if temp_source == None:
                    return

                if temp_source.find('http') == 0:
                    self.select_source(self._prev_source)
                    if self._source != None:
                        self._source = None
                        value = "OK"
                else:
                    self._lpapi.call('GET', 'setPlayerCmd:play')
                    value = self._lpapi.data
            else:
                self._lpapi.call('GET', 'setPlayerCmd:play')
                value = self._lpapi.data
                
            if value == "OK":
                self._unav_throttle = False
                self._state = STATE_PLAYING
                if self._slave_list is not None:
                    for slave in self._slave_list:
                        slave.set_state(STATE_PLAYING)
            else:
                _LOGGER.warning("Failed to start playback. Got response: %s", value)
        else:
            self._master.media_play()

    def media_pause(self):
        """Send pause command."""
        if not self._slave_mode:
            self._lpapi.call('GET', 'setPlayerCmd:onepause')
            value = self._lpapi.data
            if value == "OK":
                _LOGGER.warning("presed pause for: %s", self.entity_id)
                self._state = STATE_PAUSED
                if self._slave_list is not None:
                    for slave in self._slave_list:
                        slave.set_state(STATE_PAUSED)
            else:
                _LOGGER.warning("Failed to pause playback. Got response: %s", value)
        else:
            self._master.media_pause()

    def media_stop(self):
        """Send stop command."""
        if not self._slave_mode:
            self._lpapi.call('GET', 'setPlayerCmd:stop')
            value = self._lpapi.data
            if value == "OK":
                self._state = STATE_IDLE
                self._media_title = None
                self._prev_source = self._source
                self._source = None
                self._media_artist = None
                self._media_album = None
                self._icecast_name = None
                self._media_uri = None
                self._media_image_url = None
                if self._slave_list is not None:
                    for slave in self._slave_list:
                        slave.set_state(STATE_IDLE)
            else:
                _LOGGER.warning("Failed to stop playback. Got response: %s", value)
        else:
            self._master.media_stop()

    def media_next_track(self):
        """Send next track command."""
        if not self._slave_mode:
            self._lpapi.call('GET', 'setPlayerCmd:next')
            value = self._lpapi.data
            if value != "OK":
                _LOGGER.warning("Failed skip to next track. Got response: %s", value)
        else:
            self._master.media_next_track()

    def media_previous_track(self):
        """Send previous track command."""
        if not self._slave_mode:
            self._lpapi.call('GET', 'setPlayerCmd:prev')
            value = self._lpapi.data
            if value != "OK":
                _LOGGER.warning("Failed to skip to previous track." " Got response: %s", value)
        else:
            self._master.media_previous_track()

    def media_seek(self, position):
        """Send media_seek command to media player."""
        if not self._slave_mode:
            self._lpapi.call('GET', 'setPlayerCmd:seek:{0}'.format(str(position)))
            value = self._lpapi.data
            if value != "OK":
                _LOGGER.warning("Failed to seek. Got response: %s", value)
        else:
            self._master.media_seek(position)

    def clear_playlist(self):
        """Clear players playlist."""
        pass

    def play_media(self, media_type, media_id, **kwargs):
        """Play media from a URL or file."""
        if not self._slave_mode:
            if not media_type == MEDIA_TYPE_MUSIC:
                _LOGGER.warning("For %s Invalid media type %s. Only %s is supported", self._name, media_type, MEDIA_TYPE_MUSIC)
                return

            self._media_title = None
            self._media_artist = None
            self._media_album = None
#            self._counter_unavail = 0
            self._icecast_name = None
            self._media_image_url = None
            self._media_uri = media_id
            self._skip_throttle = True
            self._unav_throttle = False
            self._lpapi.call('GET', 'setPlayerCmd:play:{0}'.format(media_id))
            value = self._lpapi.data
            if value != "OK":
                _LOGGER.warning("Failed to play media. Got response: %s", value)
                return False
            else:
                self._state = STATE_PLAYING
                return True
        else:
            self._master.play_media(media_type, media_id)

    def select_source(self, source):
        """Select input source."""
        if not self._slave_mode:
            temp_source = next((k for k in self._source_list if self._source_list[k] == source), None)
            if temp_source == None:
                return

            self._unav_throttle = False
            if temp_source.find('http') == 0:
                self._skip_throttle = True
                self._lpapi.call('GET', 'setPlayerCmd:play:{0}'.format(temp_source))
                value = self._lpapi.data
                if value == "OK":
                    if len(self._source_list) > 1:
                        prev_source = next((k for k in self._source_list if self._source_list[k] == self._source), None)
                        if prev_source and prev_source.find('http') == -1:
                            self._wait_for_fade = True
                    self._source = source
                    self._media_uri = temp_source
                    self._state = STATE_PLAYING
                    self._media_title = None
                    self._media_artist = None
                    self._media_album = None
                    self._counter_unavail = 0
                    self._icecast_name = None
                    self._media_image_url = None
#                    _LOGGER.debug("slave_list: %s", self._slave_list)
                    if self._slave_list is not None:
                        for slave in self._slave_list:
#                            _LOGGER.debug("slave: %s", slave)
                            slave.set_source(source)
                else:
                    _LOGGER.warning("Failed to select http source and play. Got response: %s", value)
                
            else:
                self._lpapi.call('GET', 'setPlayerCmd:switchmode:{0}'.format(temp_source))
                value = self._lpapi.data
                if value == "OK":
                    self._source = source
                    self._wait_for_fade = True
                    self._media_uri = None
                    self._state = STATE_PLAYING
                    if self._slave_list is not None:
                        for slave in self._slave_list:
                            slave.set_source(source)
                else:
                    _LOGGER.warning("Failed to select source. Got response: %s", value)

            self.schedule_update_ha_state(True)

        else:
            self._master.select_source(source)
            self.schedule_update_ha_state(True)

    def select_sound_mode(self, sound_mode):
        """Set Sound Mode for device."""
        if not self._slave_mode:
            mode = list(SOUND_MODES.keys())[list(
                SOUND_MODES.values()).index(sound_mode)]
            self._lpapi.call('GET', 'setPlayerCmd:equalizer:{0}'.format(mode))
            value = self._lpapi.data
            if value == "OK":
                self._sound_mode = sound_mode
                if self._slave_list is not None:
                    for slave in self._slave_list:
                        slave.set_sound_mode(sound_mode)
            else:
                _LOGGER.warning("Failed to set sound mode. Got response: %s", value)
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
        if self._preset_key != None and preset != None:
            if not self._slave_mode:
                if int(preset) > 0 and int(preset) <= self._preset_key:
                    self._lpapi.call('GET', 'MCUKeyShortClick:{0}'.format(str(preset)))
                    value = self._lpapi.data
                    if value != "OK":
                        _LOGGER.warning("Failed to recall preset %s. " "Got response: %s", preset, value)
                else:
                    _LOGGER.warning("Wrong preset number %s. " "Has to be integer less or equal with: %s", preset, self._preset_key)
            else:
                self._master.preset_button(preset)

    def join(self, slaves):
        """Add selected slaves to multiroom configuration."""
        
        if self.entity_id not in self._multiroom_group:
            self._multiroom_group.append(self.entity_id)
            self._is_master = True
        for slave in slaves:
            if slave.entity_id not in self._multiroom_group:
                if self._multiroom_wifidierct:
                    cmd = "ConnectMasterAp:ssid={0}:ch={1}:auth=OPEN:".format(self._ssid, self._wifi_channel) + "encry=NONE:pwd=:chext=0"
                else:
                    cmd = 'ConnectMasterAp:JoinGroupMaster:eth{0}:wifi0.0.0.0'.format(self._host)
                    
                if slave.lpapi_call('GET', cmd):
                    self._multiroom_group.append(slave.entity_id)
                    slave.set_master(self)
                    slave.set_is_master(False)
                    slave.set_slave_mode(True)
                    slave.set_media_title(self._media_title)
                    slave.set_media_artist(self._media_artist)
                    slave.set_volume(self._volume)
                    slave.set_muted(self._muted)
                    slave.set_state(self.state)
                    slave.set_slave_ip(self._host)
                    slave.set_media_image_url(self._media_image_url)
                    slave.set_seek_position(self.media_position)
                    slave.set_duration(self.media_duration)
                    slave.set_position_updated_at(self.media_position_updated_at)
                    slave.set_source(self._source)
                    slave.set_sound_mode(self._sound_mode)
                else:
                    _LOGGER.warning("Failed to join multiroom from: %s", slave.entity_id)

        for slave in slaves:
            if slave.entity_id in self._multiroom_group:
                slave.set_multiroom_group(self._multiroom_group)
                slave.schedule_update_ha_state(True)
                
        self.schedule_update_ha_state(True)

    def unjoin_all(self):
        """Disconnect everybody from the multiroom configuration because i'm the master."""
        cmd = "multiroom:Ungroup"
        self._lpapi.call('GET', cmd)
        value = self._lpapi.data
        if value == "OK":
            self._is_master = False
            for slave_id in self._multiroom_group:
                for device in self.hass.data[DOMAIN].entities:
                    if device.entity_id == slave_id and device.entity_id != self.entity_id:
                        device.set_slave_mode(False)
                        device.set_is_master(False)
                        device.set_slave_ip(None)
                        device.set_master(None)
                        device.set_media_title(None)
                        device.set_media_artist(None)
#                        device.set_icon(ICON_DEFAULT)
                        device.set_state(STATE_IDLE)
                        device.set_media_image_url(None)
                        device.set_source(None)
#                        device.set_media_uri(None)
                        device.set_multiroom_group([])
                        device.schedule_update_ha_state(True)
            self._multiroom_group = []
            self.schedule_update_ha_state(True)

        else:
            _LOGGER.warning("Failed to unjoin_all multiroom. " "Got response: %s", value)
     
    def unjoin_me(self):
        """Disconnect myself from the multiroom configuration."""

        if self._multiroom_wifidierct:
            for dev in self._multiroom_group:
                for device in self.hass.data[DOMAIN].entities:
                    if device._is_master:
                        cmd = "multiroom:SlaveKickout:{0}".format(self._slave_ip)
                        self._master.lpapi_call('GET', cmd)
                        value = self._master.lpapi.data
#                        self._master.schedule_update_ha_state(True)
        else:
            cmd = "multiroom:Ungroup"
            self._lpapi.call('GET', cmd)
            value = self._lpapi.data
            self.schedule_update_ha_state(True)
            
        if value == "OK":
            if self._master is not None:
                self._master.remove_from_group(self) 
            self._master = None
            self._slave_mode = False
            self._state = STATE_IDLE
            self._media_title = None
            self._media_artist = None
            self._media_uri = None
            self._media_image_url = None
            self._source = None
            self._slave_ip = None
            self._multiroom_group = []
            
        else:
            _LOGGER.warning("Failed to unjoin_me from multiroom. " "Got response: %s", value)
     
    def remove_from_group(self, device):
        """Remove a certain device for multiroom lists."""
        if device.entity_id in self._multiroom_group:
            self._multiroom_group.remove(device.entity_id)
            self.schedule_update_ha_state(True)
            
        if self._is_master:  # update multiroom group for other members too
            for member in self._multiroom_group:
                for player in self.hass.data[DOMAIN].entities:
                    if player.entity_id == member and player.entity_id != self.entity_id:
                        player.set_multiroom_group(self._multiroom_group)
                        player.schedule_update_ha_state(True)

        if len(self._multiroom_group) <= 1:
            self._multiroom_group = []
            self._is_master = False
            self._slave_list = None
        else:
            self._slave_list.remove(device)

    def execute_command(self, command):
        """Execute desired command against the player using factory API."""
        if command.find('MCU') == 0:
            self._tcpapi.call(command)
            value = self._tcpapi.data
        elif command == 'Reboot':
            self._lpapi.call('GET', 'getStatus:ip:;reboot;')
            value = self._lpapi.data
        elif command == 'PromptEnable':
            self._lpapi.call('GET', 'PromptEnable')
            value = self._lpapi.data
        elif command == 'PromptDisable':
            self._lpapi.call('GET', 'PromptDisable')
            value = self._lpapi.data
        elif command == 'RouterMultiroomEnable':
            self._lpapi.call('GET', 'setMultiroomLogic:1')
            value = self._lpapi.data
        elif command == 'SetRandomWifiKey':
            from random import choice
            from string import ascii_letters
            newkey = (''.join(choice(ascii_letters) for i in range(16)))
            self._lpapi.call('GET', 'setNetwork:1:{0}'.format(newkey))
            value = self._lpapi.data + ", key: " + newkey
        elif command == 'WriteDeviceNameToUnit':
            self._lpapi.call('GET', 'setDeviceName:{0}'.format(self._name))
            value = self._lpapi.data + ", name: " + self._name
        elif command == 'TimeSync':
            tme = time.strftime('%Y%m%d%H%M%S')
            self._lpapi.call('GET', 'timeSync:{0}'.format(tme))
            value = self._lpapi.data + ", time: " + tme
        else:
            value = "No such command implemented."

        _LOGGER.warning("Player %s executed command: %s, result: %s", self.entity_id, command, value)

        self.hass.components.persistent_notification.async_create("<b>Executed command:</b><br>{0}<br><b>Result:</b><br>{1}".format(command, value), title=self.entity_id)

    def snapshot(self, switchinput):
        """Snapshot the current input source and the volume level of it """
        if not self._slave_mode:
            _LOGGER.warning("Player %s snapshot source: %s", self.entity_id, self._source)
            self._snap_source = self._source
            self._snap_state = self._state
            if switchinput and not self._playing_stream:
                _LOGGER.warning("Player %s snapshot switch to stream in.", self.entity_id)
                self._lpapi.call('GET', 'setPlayerCmd:switchmode:wifi')
                value = self._lpapi.data
                if value == "OK":
                    time.sleep(2)  # have to wait for the volume fade-in of the unit when physical source is changed, otherwise volume value will be incorrect
                    player_api_result = self._get_status('getPlayerStatus', no_throttle=True)
                    if player_api_result is not None:
                        try:
                            player_status = json.loads(player_api_result)
                            self._snap_volume = int(player_status['vol'])
                        except ValueError:
                            _LOGGER.warning("REST result could not be parsed as JSON")
                            self._snap_volume = 0
                    else:
                        self._snap_volume = 0
                    _LOGGER.warning("Player %s snapshot volume of the stream input: %s", self.entity_id, self._snap_volume)
                else:
                    self._snap_volume = 0
            else:
                _LOGGER.warning("Player %s snapshot stream volume: %s", self.entity_id, self._volume)
                self._snap_volume = int(self._volume)
                self._lpapi.call('GET', 'setPlayerCmd:stop')
        else:
            self._master.snapshot(switchinput)


    def restore(self):
        """Restore the current input source and the volume level of it """
        if not self._slave_mode:
            _LOGGER.warning("Player %s current source: %s, restoring volume: %s, and source to: %s", self.entity_id, self._source, self._snap_volume, self._snap_source)
            if self._snap_state != STATE_UNKNOWN:
                self._state = self._snap_state
                self._snap_state = STATE_UNKNOWN

            if self._snap_volume != 0:
                self._lpapi.call('GET', 'setPlayerCmd:vol:{0}'.format(str(self._snap_volume)))
                self._snap_volume = 0
                time.sleep(.6)

            if self._snap_source is not None:
                self.select_source(self._snap_source)
                self._snap_source = None
        else:
            self._master.restore()
                            
    def set_multiroom_group(self, multiroom_group):
        """Set multiroom group info."""
        self._multiroom_group = multiroom_group

    def set_master(self, master):
        """Set master device for multiroom configuration."""
        self._master = master

    def set_is_master(self, is_master):
        """Set master device for multiroom configuration."""
        self._is_master = is_master

    def set_slave_mode(self, slave_mode):
        """Set current device as slave in a multiroom configuration."""
        self._slave_mode = slave_mode
        self.schedule_update_ha_state(True)

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
        self.schedule_update_ha_state(True)

    def set_sound_mode(self, mode):
        """Set the sound mode property."""
        self._sound_mode = mode

    def set_media_image_url(self, url):
        """Set the media image URL property."""
        self._media_image_url = url
        
    def set_media_uri(self, uri):
        """Set the media URL property."""
        self.set_media_uri = uri

    def lpapi_call(self, method, cmd):
        """Set the media image URL property."""
        self._lpapi.call(method, cmd)
        value = self._lpapi.data
        if value == "OK":
            return True
        else:
            _LOGGER.warning("Failed to run received command: %s, response %s", cmd, value)

    def _is_playing_new_track(self, status):
        """Check if track is changed since last update."""
#        _LOGGER.debug('is_playing_new_track %s _media_artist %s', self._name, self._media_artist)
#        _LOGGER.debug('is_playing_new_track %s _media_prev_artist %s', self._name, self._media_prev_artist)
#        _LOGGER.debug('is_playing_new_track %s _media_title %s', self._name, self._media_title)
#        _LOGGER.debug('is_playing_new_track %s _media_prev_title %s', self._name, self._media_prev_title)
        if self._media_artist != self._media_prev_artist or self._media_title != self._media_prev_title:
            return True
        else:
            return False

    @Throttle(UNA_THROTTLE)
    def _get_status(self, status):
        #_LOGGER.debug('getting status for %s', self._name)
        self._lpapi.call('GET', status)
        return self._lpapi.data

    def _update_via_upnp(self):
        """Update track info via UPNP."""
        import validators
#        self._media_prev_artist = self._media_artist
#        self._media_prev_title = self._media_title
        self._media_title = None
        self._media_album = None
        self._media_artist = None
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
#            self._media_prev_artist = self._media_artist
#            self._media_prev_title = self._media_title
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
            self._media_image_url = None

    @Throttle(ICE_THROTTLE)
    def _update_from_icecast(self):
        """Update track info from icecast stream."""
        if self._icecast_meta == 'Off':
            return True
#        _LOGGER.debug('Looking for IceCast metadata: %s', self._name)

        def NiceToICY(self):
            class InterceptedHTTPResponse():
                pass
            import io
            line = self.fp.readline().replace(b"ICY 200 OK\r\n", b"HTTP/1.0 200 OK\r\n")
            InterceptedSelf = InterceptedHTTPResponse()
            InterceptedSelf.fp = io.BufferedReader(io.BytesIO(line))
            InterceptedSelf.debuglevel = self.debuglevel
            InterceptedSelf._close_conn = self._close_conn
            return ORIGINAL_HTTP_CLIENT_READ_STATUS(InterceptedSelf)
        
        ORIGINAL_HTTP_CLIENT_READ_STATUS = urllib.request.http.client.HTTPResponse._read_status
        urllib.request.http.client.HTTPResponse._read_status = NiceToICY

        try:
            request = urllib.request.Request(self._media_uri, headers={'Icy-MetaData': 1})  # request metadata
            response = urllib.request.urlopen(request)
        except (urllib.error.HTTPError):  #urllib.error.
            self._media_title = None
            self._media_artist = None
            self._icecast_name = None
            self._media_image_url = None
            return True

        icy_name = response.headers['icy-name']
        if icy_name is not None and icy_name != 'no name' and icy_name != 'Unspecified name':
            try:  # 'latin1' # default: iso-8859-1 for mp3 and utf-8 for ogg streams
                self._icecast_name = icy_name.encode('latin1').decode('utf-8')
            except (UnicodeDecodeError):
                self._icecast_name = icy_name

        else:
            self._icecast_name = None

        if self._icecast_meta == 'StationName':
            self._media_title = self._icecast_name
            self._media_artist = None
            self._media_image_url = None
            return True

        import re
        import struct
        import chardet
        icy_metaint_header = response.headers['icy-metaint']
        if icy_metaint_header is not None:
            metaint = int(icy_metaint_header)
            for _ in range(10):  # title may be empty initially, try several times
                response.read(metaint)  # skip to metadata
                metadata_length = struct.unpack('B', response.read(1))[0] * 16  # length byte
                metadata = response.read(metadata_length).rstrip(b'\0')
                # extract title from the metadata
                m = re.search(br"StreamTitle='([^']*)';", metadata)
                if m:
                    title = m.group(1)
                    if title:
                        code_detect = chardet.detect(title)['encoding']
                        title = title.decode(code_detect, errors='ignore')
                        title = re.sub(r'\[.*?\]\ *', '', title)  #  "\s*\[.*?\]\s*"," ",title)
                        if title.find(' - ') != -1:
                            titles = title.split(' - ')
                            self._media_artist = titles[0].strip()
                            self._media_title = titles[1].strip()
                        else:
                            if self._icecast_name is not None:
                                self._media_artist = '[' + self._icecast_name + ']'
                            else:
                                self._media_artist = None
                            self._media_title = title
                        break
                else:
                    if self._icecast_name is not None:
                        self._media_title = self._icecast_name
                    else:
                        self._media_title = None
                    self._media_artist = None
                    self._media_image_url = None

        else:
            if self._icecast_name is not None:
                self._media_title = self._icecast_name
            else:
                self._media_title = None
            self._media_artist = None
            self._media_image_url = None

    def _get_lastfm_coverart(self):
        """Get cover art from last.fm."""
        
        self._lfmapi.call('GET', 'track.getInfo', "artist={0}&track={1}".format(self._media_artist, self._media_title))
        lfmdata = json.loads(self._lfmapi.data)
        try:
            self._media_image_url = lfmdata['track']['album']['image'][3]['#text']
        except (ValueError, KeyError):
            self._media_image_url = None
        if self._media_image_url == '':
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

    def update(self):
        """Get the latest player details from the device."""

        if self._slave_mode:
            return True

#        if self._counter_unavail > 0 and self._counter_unavail <= UNAVAIL_MAX:
#            # a counter to try to reconnect to unavailable devices from time to time, but not continuously
#            self._counter_unavail = self._counter_unavail + 1
#            return True

#        self._counter_unavail = 0
        
        if self._wait_for_fade:  # have wait for the volume fade-in of the unit when source is changed, otherwise volume value will be incorrect
            if self._media_uri:
                time.sleep(2)    # switching to a stream time to display correct vol value
            else:
                time.sleep(.6)   # switching to a physical input time to display correct vol value
            self._wait_for_fade = False

        if self._upnp_device is None and self._devicename is not None:
            for entry in self.upnp_discover(UPNP_TIMEOUT):
                if entry.friendly_name == self._devicename:
                    self._upnp_device = upnpclient.Device(entry.location)
                    break

#        self._lpapi.call('GET', 'getPlayerStatus')
 #       player_api_result = self._lpapi.data

        if self._unav_throttle:
            player_api_result = self._get_status('getPlayerStatus')
        else:
            player_api_result = self._get_status('getPlayerStatus', no_throttle=True)

        if player_api_result is None:
            # _LOGGER.warning('Unable to connect to device')
            self._unav_throttle = True
            self._counter_unavail = 1
            self._state = STATE_UNAVAILABLE  # STATE_UNKNOWN
            self._media_artist = None
            self._media_album = None
            self._media_image_url = None
            self._media_uri = None
            self._icecast_name = None
            self._source = None
            return True

        try:
            player_status = json.loads(player_api_result)
        except ValueError:
            _LOGGER.warning("REST result could not be parsed as JSON")


        if isinstance(player_status, dict):
            self._unav_throttle = False
            if self._multiroom_wifidierct:
                self._lpapi.call('GET', 'getStatus')
                device_api_result = self._lpapi.data
                if device_api_result is not None:
                    try:
                        device_status = json.loads(device_api_result)
                    except ValueError:
                        # _LOGGER.warning("REST result could not be parsed as JSON")
                        _LOGGER.debug("Erroneous JSON: %s", device_api_result)
                        device_status = None

                    if isinstance(device_status, dict):
                        self._wifi_channel = device_status['WifiChannel']
                        self._ssid = binascii.hexlify(device_status['ssid'].encode('utf-8'))
                        self._ssid = self._ssid.decode()
    
            if player_status['mode'] == 99:
                self._slave_mode = True
                return True

            # Update variables that changes during playback of a track.
            self._volume = player_status['vol']
            self._muted = bool(int(player_status['mute'])) 
            self._seek_position = int(int(player_status['curpos']) / 1000)
            self._position_updated_at = utcnow()

            try:
                if player_status['uri'] != "":
                    self._media_uri = str(bytearray.fromhex(player_status['uri']).decode('utf-8'))
                else:
                    self._media_uri = None

            except KeyError:
                pass

            self._state = {
                'stop': STATE_IDLE,
                'play': STATE_PLAYING,
                'pause': STATE_PAUSED,
                'load': STATE_PLAYING,
            }.get(player_status['status'], STATE_UNKNOWN)
            
            source_t = SOURCES_MAP.get(player_status['mode'], 'WiFi')
            source_n = self._source_list.get(source_t.lower(), None)
            
            if source_n != None:
                self._source = source_n
            else:
                self._source = source_t
            
            if self._source != "WiFi" and not self._media_uri:
                if self._source == "Idle":
                    self._media_title = None
                    self._state = STATE_IDLE
                else:
                    self._media_title = self._source

                self._media_artist = None
                self._media_album = None
                self._media_image_url = None
                self._icecast_name = None

            self._sound_mode = SOUND_MODES.get(player_status['eq'])

            self._shuffle = {
                '2': True,
                '3': True,
            }.get(player_status['loop'], False)

            self._playing_spotify = bool(player_status['mode'] == '31')
            self._playing_stream = bool(player_status['mode'] == '10')
            
            if self._playing_spotify:
                self._state = STATE_PLAYING
                self._update_via_upnp()

            elif self._media_uri and int(player_status['totlen']) <= 0 and player_status['mode'] != 1 and player_status['mode'] != 2 and player_status['mode'] != 3:
                self._source = self._source_list.get(self._media_uri, 'WiFi')
                if player_status['status'] != 'pause':
                    if self._skip_throttle:
                        self._update_from_icecast(no_throttle=True)
                        self._skip_throttle = False
                    else:
                        self._update_from_icecast()
                    self._new_song = self._is_playing_new_track(player_status)
                    self._state = STATE_PLAYING
                    if self._lfmapi is not None and self._new_song and self._media_title is not None and self._media_artist is not None:
                        self._get_lastfm_coverart()
                    elif self._media_title is None or self._media_artist is None:
                        self._media_image_url = None

            elif self._media_uri and self._new_song and not self._playing_stream:  # player_status['mode'] != 10:
                self._update_from_id3()
                self._new_song = self._is_playing_new_track(player_status)
                if self._lfmapi is not None and self._media_title is not None and self._media_artist is not None:
                    self._get_lastfm_coverart()
                else:
                    self._media_image_url = None

            self._media_prev_artist = self._media_artist
            self._media_prev_title = self._media_title
            self._duration = int(int(player_status['totlen']) / 1000)

        else:
            _LOGGER.warning("JSON A result was not a dictionary")

#        if not self._first_update or not self._multiroom_wifidierct:
#            return True
#        else:
#            self._first_update = False
            
       # Get multiroom slave information #
        self._lpapi.call('GET', 'multiroom:getSlaveList')
        slave_list = self._lpapi.data
        if slave_list is None:
            self._is_master = False
            self._slave_list = None
            self._multiroom_group = []
            return True

        try:
            slave_list = json.loads(slave_list)
        except ValueError:
            # _LOGGER.warning("REST result could not be parsed as JSON")
            _LOGGER.debug("Erroneous JSON: %s", slave_list)
            slave_list = None
            self._slave_list = None
            self._multiroom_group = []
	
        self._slave_list = []
        self._multiroom_group = []
        if isinstance(slave_list, dict):
            if int(slave_list['slaves']) > 0:
#                _LOGGER.debug("Salve list: %s", slave_list)
                self._multiroom_group.append(self.entity_id)
                self._is_master = True
                for slave in slave_list['slave_list']:
#                    _LOGGER.debug("SLAVE: %s", slave)
                    for device in self.hass.data[DOMAIN].entities:
                        if device._name == slave['name']:
#                            _LOGGER.debug("SLAVE NAME: %s", device._name)
                            self._multiroom_group.append(device.entity_id)
                            device.set_master(self)
                            device.set_is_master(False)
                            device.set_slave_mode(True)
                            device.set_media_title(self._media_title)
                            device.set_media_artist(self._media_artist)
                            device.set_volume(slave['volume'])
                            device.set_muted(slave['mute'])
                            device.set_state(self.state)
                            device.set_slave_ip(slave['ip'])
                            device.set_media_image_url(self._media_image_url)
                            device.set_seek_position(self.media_position)
                            device.set_duration(self.media_duration)
                            device.set_position_updated_at(self.media_position_updated_at)
                            device.set_source(self._source)
                            device.set_sound_mode(self._sound_mode)

                    for slave in slave_list['slave_list']:
                        for device in self.hass.data[DOMAIN].entities:
                            if device.entity_id in self._multiroom_group:
                                device.set_multiroom_group(self._multiroom_group)

        else:
            _LOGGER.warning("JSON B result was not a dictionary")

        return True


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

#        _LOGGER.debug("Updating LinkPlayRestData from %s", self._request.url)
        try:
            with requests.Session() as sess:
                response = sess.send(
                    self._request, timeout=5)
            self.data = response.text

        except requests.exceptions.RequestException as ex:
#            _LOGGER.warning("Error fetching data: %s from %s failed with %s", self._request, self._request.url, ex)
            self.data = None

class LinkPlayTcpUartData:
    """Class for handling the data retrieval from the LinkPlay device."""

    def __init__(self, host):
        """Initialize the data object."""
        self.data = None
        self._host = host

    def call(self, cmd):
        """Get the latest data from TCP service."""
        HEAD = '18 96 18 20 0b 00 00 00 c1 02 00 00 00 00 00 00 00 00 00 00 '
        CMHX = ' '.join(hex(ord(c))[2:] for c in cmd)
        self.data = None
#        _LOGGER.warning("Sending to %s TCP command: %s", self._host, cmd)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((self._host, TCPPORT))
                s.send(bytes.fromhex(HEAD + CMHX))
                data = str(repr(s.recv(1024))).encode().decode("unicode-escape")
            
            pos = data.find("AXX")
            if pos == -1:
                pos = data.find("MCU")

            self.data = data[pos:(len(data)-2)]
#            _LOGGER.warning("Received from %s TCP command result: %s", self._host, self.data)
            try:
                s.close()
            except:
                pass

        except socket.error as ex:
#            _LOGGER.warning("Error sending TCP command: %s with %s", cmd, ex)
            self.data = None

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
        _LOGGER.debug("Updating LastFMRestData from %s", self._request.url)

        try:
            with requests.Session() as sess:
                response = sess.send(
                    self._request, timeout=10)
            self.data = response.text

        except requests.exceptions.RequestException as ex:
            # _LOGGER.warning("Error fetching data: %s from %s failed with %s", self._request, self._request.url, ex)
            self.data = None
