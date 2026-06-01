# Agent Prompt Files

This directory is the version-controlled prompt root for trading-agent prompts.

Prompt files must be YAML and include:

- `prompt_id`
- `prompt_version`
- `pipeline_name`
- `output_schema_id`
- `output_schema_version`
- `template`

The trading prompt registry records template and rendered prompt hashes so LLM
outputs can be audited with the prompt and schema versions used for a run.
