# Cloud-first operation from a tablet

This pilot runs on GitHub-hosted Linux runners. Your Lenovo tablet only needs a browser; no local Python, FFmpeg, Ollama, or always-on computer is required.

## 1. Add provider API keys as GitHub Actions secrets
Open **Settings → Secrets and variables → Actions → New repository secret** and add:
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`

These are paid API services in most cases and are billed separately from ChatGPT, Claude, or Gemini web subscriptions. Never put keys in code, issue comments, Make scenario data, or chat messages.

## 2. Enable the workflow
GitHub only allows a manually dispatched workflow to be run reliably once its workflow file is present on the repository's default branch. Open the pull request for this branch, inspect it, and merge it into `main` when you are comfortable with the untested pilot. Do not enable any public publishing.

## 3. Run the first video from your tablet
Open **Actions → Cloud Arabic Video Pilot → Run workflow**.
- Topic: `مهنة الطبيب: كيف يساعد الناس؟`
- Channel: `children`
- Run workflow.

After completion, open the run and download the `arabic-video-review` artifact. It contains the MP4, script, and two reviewer decisions. If either reviewer rejects, rendering stops and the review JSON remains available as an artifact.

## 4. What each agent does
- OpenAI: drafts a four-scene Arabic script and image prompts.
- Claude: independently reviews safety and editorial quality.
- Gemini: independently reviews safety and factual-risk issues.
- GitHub Actions: runs the workflow and renders a vertical MP4 using FFmpeg and Arabic TTS.
- You: review the first artifact before public posting.

## 5. Make integration
Create a Make scenario with a Scheduler module, then an HTTP > Make a request module:
- Method: `POST`
- URL: `https://api.github.com/repos/believeingchild-cmd/arabic-ai-media-agents/actions/workflows/cloud-arabic-video.yml/dispatches`
- Headers: `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, and `Authorization: Bearer YOUR_FINE_GRAINED_TOKEN`
- Body type: JSON; body example: `{"ref":"main","inputs":{"topic":"مهنة الطبيب: كيف يساعد الناس؟","channel":"children"}}`
- Use a fine-grained GitHub token limited to this repository with Actions: write permission. Keep it in Make's secret/connection settings, never in a public variable or this repository.
- Then poll GitHub's workflow runs API and notify you when the run completes; download the artifact link from the run page. Create a narrowly scoped GitHub token and store it only in Make's connection/secret vault. Do not add the token to this repository. Do not expose a webhook or dashboard publicly.

## Limitations
- This is a pilot; public publishing is intentionally disabled.
- A third-party image endpoint is used for visual drafts; availability, content rights, and suitability need review. Replace it with a provider whose terms and rights fit your channel before scaling.
- AI reviewers can miss mistakes. Religious claims need trustworthy references; news content needs current independent sources. The public-channel mode therefore should not be used for breaking news until source retrieval and citation checks are implemented.
- TikTok/Instagram/YouTube posting still needs official platform credentials, approvals, and a separate publish gate.
- The GitHub workflow has not been executed in this editing session. Confirm dependency/API compatibility in the first run before relying on it.
