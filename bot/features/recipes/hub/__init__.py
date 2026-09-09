"""Hub feature package: registered recipes and process helpers.

Classification (Architecture Contract Phase 5):

**Registered recipes** (also listed in ``bot.app.features.loader.RECIPE_MODULES``):
- ``initialize`` / ``uninitialize`` / ``migrate`` / ``installs`` / ``data_reset``
- ``announcements`` / ``client_announcements``

These are complete hub processes invoked via ``recipe_context.run(...)`` from domain
entry recipes (``server.*``, ``relay.*``, …) or event recipes. They stay registered
so nesting, validation, and error boundaries remain uniform.

**Feature helpers** (not registered; imported by recipes above):
- ``probe``, ``leaders``, ``reconcilers``, ``changelog``, ``notifications``, ``result``
- ``clients/`` (provision, deletion, profile, subscription, rectification, …)
- ``onboarding/``, ``network/``, ``relay/``

Helpers know The Network vocabulary and call core workhorses. Do not register them
as recipes unless they become independently triggered application operations.
"""
