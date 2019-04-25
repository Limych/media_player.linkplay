*Please :star: this repo if you find it useful*

# LinkPlay devices integration for Home Assistant

[… … … This is just skeleton for now, sorry]

I also suggest you [visit the support topic](https://community.home-assistant.io/t/linkplay-integration/33878) on the community forum.

## Component setup instructions

1. Create a directory `custom_components` in your Home Assistant configuration directory.

1. Create a directory `linkplay` in `custom_components` directory.

1. Copy [linkplay directory](https://github.com/Limych/media_player.linkplay/tree/master/custom_components/media_player.linkplay) from this project including **all** files and sub-directories into the directory `custom_components`.

    It should look similar to this after installation:
    ```
    <config_dir>/
    |-- custom_components/
    |   |-- media_player.linkplay/
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
