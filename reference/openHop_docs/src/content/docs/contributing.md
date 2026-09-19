---
title: Contributing
description: How to add and format Markdown or MDX pages in openHop Docs.
---

This site is Markdown-first, with MDX used when a page needs components or JSX.
Adding an ordinary page should be simple.

## Add a new page

1. Create a `.md` file for ordinary content, or `.mdx` only when the page needs
   imported components or JSX, under one of these directories:
   - `src/content/docs/projects/openhop-core/`
   - `src/content/docs/projects/openhop-repeater/`
   - `src/content/docs/projects/openhop-modem/`
   - `src/content/docs/projects/openhop-ha-integration/`
   - `src/content/docs/projects/openhop-ha-addon/`
   - `src/content/docs/projects/openhop-unraid/`
2. Add frontmatter:

```md
---
title: Your Page Title
description: One-line summary shown in metadata and previews.
---
```

3. Write content using standard Markdown, or MDX where required.
4. Run `npm run dev` and verify the page appears in the sidebar. This command
   runs the OpenAPI synchronization hook and may update the tracked
   `public/openapi/repeater.yaml` file from a sibling Repeater checkout. Inspect
   that diff before committing and use the exact-ref workflow in
   [LOCAL_DEVELOPMENT.md](https://github.com/openhop-dev/openHop_docs/blob/dev/LOCAL_DEVELOPMENT.md)
   when reproducibility matters.
5. Open a pull request.

## Naming conventions

- Use lowercase file names with hyphens.
- Keep one topic per page.
- Prefer short sections and scannable headings.

## Authoring tips

- Use admonitions for warnings and notes.

```md
:::note
This behavior depends on hardware and region settings.
:::
```

- Use fenced code blocks with language identifiers.
- Link to source repositories for deep implementation details.

## Current project sections

- openHop Core
- openHop Repeater
- openHop Modem
- openHop HA Integration
- openHop HA Add-on
- openHop Unraid
