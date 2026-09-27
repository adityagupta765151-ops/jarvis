"""JARVIS — a voice-controlled desktop assistant.

    app/      settings, the assistant loop, live readings
    voice/    speech in, speech out, the wake word
    routing/  the fast lane that answers without the model
    ai/       the model provider, the tool-calling brain, the planner, the prompts
    tools/    what it can actually do, one module per domain
    store/    what it remembers between sessions
    jobs/     resume, job search, matching, applications, dashboard

A command travels: voice -> wake word -> routing -> ai -> tools -> voice.
"""
