# Dead-code whitelist for tools/code_health.py (vulture), one dotted name per line with the
# reason vulture cannot see the use. Names reached through a decorator (command handlers,
# validators, event listeners, fixtures) never need a line here: the tool ignores those
# decorators. Every line below is counted by the code_health.dead_code_whitelisted ceiling in
# .ratchets/code_health.txt, so this list only shrinks without a recorded reason.
from insightminer import ports, settings

WHITELISTED = (
    ports.ProcessRunner.spawn,  # port method: implemented by the adapter, called from web at M2
    settings._YamlStaticSource.get_field_value,  # pydantic-settings source hook, framework-called
    settings.Settings.settings_customise_sources,  # pydantic-settings hook, called by the framework
)
