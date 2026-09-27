import gradio as gr
import uvicorn
from my_work.bot import app as bot_app

try:
    import spaces
    @spaces.GPU
    def init_gpu():
        return True
except Exception:
    pass

with gr.Blocks(title="magicpin Vera AI Bot") as demo:
    gr.Markdown("# 🚀 magicpin Vera AI Bot is Active")
    gr.Markdown("""
    ### Live Judge Endpoints:
    - **`GET /v1/healthz`** — Liveness probe
    - **`GET /v1/metadata`** — Bot metadata
    - **`POST /v1/context`** — Context ingestion
    - **`POST /v1/tick`** — Outbound composer
    - **`POST /v1/reply`** — Multi-turn conversation handler
    """)

# Mount Gradio onto the existing FastAPI app at /ui
app = gr.mount_gradio_app(bot_app, demo, path="/ui")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
