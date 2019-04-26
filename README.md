*Please :star: this repo if you find it useful*

# LinkPlay devices integration for Home Assistant

This component allows you to integrate control of audio devices based on LinkPlay platform into your Home Assistant smart home system.

LinkPlay platform makes it easy to create a variety of modern audio systems. There are already quite a few manufacturers and devices that operate on the basis of LinkPlay. Here are just some of the firms and devices:
**August** (WS300G),
**Auna** (Intelligence Tube),
**Bauhn** (SoundMax 5),
**Bem** (Speaker Big Mo),
**Centaurus** (Flyears),
**Champion** (AWF320),
**COWIN** (DiDa, Thunder),
**Crystal Acoustics** (Crystal Audio),
**CVTE** (FD2140),
**Dayton Audio** (AERO),
**DOSS** (Deshi, Soundbox Mini, DOSS Assistant, Cloud Fox A1),
**DYON** (DYON Area Player),
**Edifier** (MA1),
**Energy Sistem** (Multiroom Tower Wi-Fi, Multiroom Portable Wi-Fi),
**FABRIQ** (Chorus, Riff),
**First Alert** (Onelink Safe & Sound),
**GE Sol** (C),
**GGMM** (E5 Wireless, E3 Wireless),
**GIEC** (Hi-Fi Smart Sound S1),
**Harman Kardon** (Allure),
**Hyundai** (Modern Oxygen Bar),
**iDeaUSA** (iDEaHome, Home Speaker, Mini Home Soundbar),
**iEast** (SoundStream, Stream Pro, StreamAmp AM160, StreamAmp i50B)
**iHome** (iAVS16),
**iLive** (Concierge, Platinum),
**iLuv** (Aud Air, Aud Click Shower, Aud Click),
**JAM Audio** (Voice, Symphony, Rhythm),
**JD** (CrazyBoa 2Face),
**Lowes** (Showbox),
**Magnavox** (MSH315V),
**Medion** (MD43631, MedionX MD43259),
**Meidong** (Meidong 3119),
**MK** (MK Alexa Speaker),
**MÜZO** (Cobblestone),
**Naxa** (NAS-5003, NHS-5002, NAS-5001, NAS-5000),
**Nexum** (Memo),
**Omaker** (WoW),
**Omars** (Dogo),
**Polaroid** (PWF1001),
**Sharper Image** (SWF1002),
**Shenzhen Renqing Technology Ltd** (ROCKLAVA),
**SoundBot** (SB600),
**SoundLogic** (Buddy),
**Tibo** (Choros Tap),
**Tinman** (Smart JOJO),
**Uyesee** (AM160),
**Youzhuan** (Intelligent Music Ceiling),
**Zolo Audio** (Holo),

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

[… … … This is just skeleton for now, sorry]

### Configuration Variables

[… … … This is just skeleton for now, sorry]
  
**entities:**\
  *(list)* *(Required)* A list of temperature sensor entity IDs.
  
  *NB* You can use weather provider entity as a data source.  

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
