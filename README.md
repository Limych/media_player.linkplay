*Please :star: this repo if you find it useful*

# LinkPlay devices integration for Home Assistant

***Collaborators wanted!** This component was transferred to this repository to save from death as a result of moral obsolescence of the code. But now I don’t have the opportunity to fully support it and develop the code.*

*If you can help with developing this component, I will be very grateful to you.  Please, message to me.*
<p align="center">* * *</p>

This component allows you to integrate control of audio devices based on LinkPlay platform into your Home Assistant smart home system.

![](https://raw.githubusercontent.com/Limych/media_player.linkplay/master/docs/images/linkplay_logo.png)

![](https://raw.githubusercontent.com/Limych/media_player.linkplay/master/docs/images/linkplay_devices.png)

LinkPlay platform makes it easy to create a variety of modern audio systems. There are already quite a few manufacturers and devices that operate on the basis of LinkPlay. Here are just some of the firms and devices:

* August (WS300G)
* Auna (Intelligence Tube)
* Bauhn (SoundMax 5)
* Bem (Speaker Big Mo)
* Centaurus (Flyears)
* Champion (AWF320)
* COWIN (DiDa Thunder)
* Crystal Acoustics (Crystal Audio)
* CVTE (FD2140)
* Dayton Audio (AERO)
* DOSS (Deshi Soundbox Mini DOSS Assistant Cloud Fox A1)
* DYON (DYON Area Player)
* Edifier (MA1)
* Energy Sistem (Multiroom Tower Wi-Fi Multiroom Portable Wi-Fi)
* FABRIQ (Chorus Riff)
* First Alert (Onelink Safe & Sound)
* GE Sol (C)
* GGMM (E2 Wireless E3 Wireless E5 Wireless)
* GIEC (Hi-Fi Smart Sound S1)
* Harman Kardon (Allure)
* Hyundai (Modern Oxygen Bar)
* iDeaUSA (iDEaHome Home Speaker Mini Home Soundbar)
* iHome (iAVS16)
* iLive (Concierge Platinum)
* iLuv (Aud Air Aud Click Shower Aud Click)
* JAM Audio (Voice Symphony Rhythm)
* JD (CrazyBoa 2Face)
* Lowes (Showbox)
* Magnavox (MSH315V)
* Medion (MD43631 MedionX MD43259)
* Meidong (Meidong 3119)
* MK (MK Alexa Speaker)
* MÜZO ([Cobblestone](https://www.arylic.com/products/muzo-cobblestone-wifi-pre-amp-with-airplay-dlna-spotify-connect))
* Naxa (NAS-5003 NHS-5002 NAS-5001 NAS-5000)
* Nexum (Memo)
* Omaker (WoW)
* Omars (Dogo)
* Polaroid (PWF1001)
* Roxcore	(Roxcore)
* Sharper Image (SWF1002)
* Shenzhen Renqing Technology Ltd (ROCKLAVA)
* Sonoé (iEast SoundStream iEast Stream Pro iEast StreamAmp AM160 iEast StreamAmp i50B)
* SoundBot (SB600)
* SoundLogic (Buddy)
* Stereoboommm (MR200 MR300)
* Tibo (Choros Tap)
* Tinman (Smart JOJO)
* Venz (A501)
* Uyesee (AM160)
* Youzhuan (Intelligent Music Ceiling)
* Zolo Audio (Holo)
* etc.

I also suggest you [visit the support topic](https://community.home-assistant.io/t/linkplay-integration/33878) on the community forum.

## Component setup instructions

1. Create a directory `custom_components` in your Home Assistant configuration directory.

1. Create a directory `linkplay` in `custom_components` directory.

1. Copy [linkplay directory](https://github.com/Limych/media_player.linkplay/tree/master/custom_components/media_player.linkplay) from this project including **all** files and sub-directories into the directory `custom_components`.

    It should look similar to this after installation:
    ```
    <config_dir>/
    |-- custom_components/
    |   |-- linkplay/
    |       |-- __init__.py
    |       |-- manifest.json
    |       |-- etc...
    ```


1. To add LinkPlay device to your installation, add the following to your `configuration.yaml` file:
    
    ```yaml
    # Example configuration.yaml entry
    media_player:
      - platform: linkplay
        host: YOUR_IP_ADDRESS 
        device_name: NAME_OF_DEVICE_AS_IN_OFFICIAL_APPLICATION 
    ```

### Configuration Variables
  
**host:**\
  *(string)* *(Required)* The host name or IP address of the device that is running Emby.
  
**device_name:**\
  *(string)* *(Required)* The name of the device, as it setted up in the official application.

**name:**\
  *(string)* *(Optional)* Name to use in the frontend.\
  *Default value: Identical to devicename value*

**lastfm_api_key:**\
  *(string)* *(Optional)* API key to LastFM service to get album covers.

## Track updates

You can automatically track new versions of this component and update it by [custom-updater](https://github.com/custom-components/custom_updater).

To initiate tracking add this lines to you `configuration.yaml` file:

```yaml
# Example configuration.yaml entry
custom_updater:
  track:
    - components
  component_urls:
    - https://raw.githubusercontent.com/Limych/media_player.linkplay/master/custom_components.json
```
