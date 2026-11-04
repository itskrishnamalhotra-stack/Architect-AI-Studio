# Security and privacy

This is a locally hosted concept-design application. It does not provide user accounts, remote storage, or managed multi-user authentication. Do not expose the FastAPI server directly to the public Internet without adding security, authentication, reverse proxy protections, request limits, logging policies, and deployment hardening.

- Set `GEMINI_API_KEY` as a server-side environment variable only. Never include real API keys in frontend JavaScript, `.env.example`, screenshots or example JSON.
- The local draft feature uses browser storage on the current browser/device. Export JSON if you need a durable, portable backup.
- Do not upload confidential client floor plans or personal data to a public repository.
- SVG, DXF and JSON are exported outputs, not proof of safety or building-code compliance.
- Create a private repository until code ownership and external dependencies have been reviewed.

To report a suspected vulnerability, contact the repository owner privately rather than posting secrets or exploit details in a public issue.
