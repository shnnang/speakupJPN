import streamlit as st
import streamlit.components.v1 as components
import edge_tts
import asyncio
from io import BytesIO
import base64
import json

st.set_page_config(page_title="読み上げ（B: edge-tts 単語ハイライト）", page_icon="🗣️", layout="centered")
st.title("🗣️ 読み上げ（B: edge-tts）単語ハイライト + クリック再生")

text = st.text_area("文章を貼り付け", height=220, placeholder="ここに日本語の文章を貼り付け…")

# ====== 設定 ======
voice = st.selectbox(
    "音声",
    ["ja-JP-KeitaNeural", "ja-JP-NanamiNeural", "ja-JP-DaichiNeural", "ja-JP-AoiNeural"],
    index=0
)

col1, col2 = st.columns(2)
gen_rate = col1.slider("生成時の話速（edge-tts rate %）", -50, 50, 0, 5)
playback_rate = col2.slider("再生時の倍速（audio.playbackRate）", 0.5, 2.0, 1.0, 0.1)

def fmt_rate(x: int) -> str:
    return f"{x:+d}%"

async def synthesize_word_boundary_async(txt: str, voice: str, rate_percent: int):
    """
    boundary="WordBoundary" にして stream() から audio と WordBoundary を拾う。
    stream() が audio と WordBoundary を流す例が公式の例/ドキュメントにある。[1](https://gtts.readthedocs.io/en/latest/)[5](https://model.aibase.com/ja/models/details/1915692899666386945)
    """
    communicate = edge_tts.Communicate(
        txt,
        voice=voice,
        rate=fmt_rate(rate_percent),
        boundary="WordBoundary",  # 単語境界イベント[5](https://model.aibase.com/ja/models/details/1915692899666386945)[1](https://gtts.readthedocs.io/en/latest/)
    )

    audio_buf = BytesIO()
    marks = []  # {offset, duration, text}

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_buf.write(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            marks.append({
                "offset": chunk["offset"],
                "duration": chunk["duration"],
                "text": (chunk.get("text") or "")
            })

    return audio_buf.getvalue(), marks

def synthesize_word_boundary(txt: str, voice: str, rate_percent: int):
    try:
        return asyncio.run(synthesize_word_boundary_async(txt, voice, rate_percent))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(synthesize_word_boundary_async(txt, voice, rate_percent))
        finally:
            loop.close()

if st.button("🎧 生成して表示", type="primary"):
    if not text.strip():
        st.warning("文章を入力してね！")
        st.stop()

    with st.spinner("生成中…"):
        mp3_bytes, marks = synthesize_word_boundary(text, voice, gen_rate)

    # 音声を base64 にしてHTMLに埋め込み
    b64_audio = base64.b64encode(mp3_bytes).decode("utf-8")

    # offset/duration は 100ns ticks → 秒へ変換: ticks / 10,000,000 [2](https://deepwiki.com/nateshmbhat/pyttsx3/2.2.1-sapi5-driver-%28windows%29)
    cues = []
    for m in marks:
        t = (m["text"] or "").strip()
        if not t:
            continue
        start = m["offset"] / 10_000_000
        end = (m["offset"] + m["duration"]) / 10_000_000
        cues.append({"start": start, "end": end, "text": t})

    if not cues:
        st.error("WordBoundaryが取得できませんでした（ネットワーク制限などの可能性）。")
        st.stop()

    cues_json = json.dumps(cues, ensure_ascii=False)

    html = f"""
    <style>
      .word {{
        display:inline-block; padding:3px 6px; margin:3px 2px 0 0;
        border-radius:10px; border:1px solid #e5e7eb; cursor:pointer;
        font-size:14px; line-height:1.7; user-select:none;
      }}
      .word.active {{
        background:#dbeafe; border-color:#60a5fa;
        box-shadow:0 0 0 2px rgba(96,165,250,0.25);
      }}
      .toolbar {{ display:flex; gap:10px; align-items:center; margin:10px 0 8px; flex-wrap:wrap; }}
      .btn {{
        padding:6px 10px; border-radius:10px; border:1px solid #ddd; cursor:pointer; background:white;
      }}
      .muted {{ color:#6b7280; font-size:12px; }}
      .panel {{ margin-top:10px; }}
    </style>

    <div class="toolbar">
      <button class="btn" id="play">▶️ 再生</button>
      <button class="btn" id="pause">⏸ 一時停止</button>
      <button class="btn" id="stop">⏹ 停止</button>
      <span class="muted">再生速度: <b id="rateLabel">{playback_rate:.1f}x</b></span>
      <span class="muted">（単語をクリックすると、そこから再生）</span>
    </div>

    <audio id="player" controls style="width:100%;">
      data:audio/mpeg;base64,{b64_audio}
    </audio>

    <div class="panel" id="panel"></div>

    <script>
      const cues = {cues_json};
      const playbackRate = {playback_rate};
      const player = document.getElementById("player");
      const panel = document.getElementById("panel");
      const rateLabel = document.getElementById("rateLabel");

      // 再生速度（HTMLAudioElementの機能）[4](https://huggingface.co/coqui/XTTS-v2)
      player.playbackRate = playbackRate;
      rateLabel.textContent = playbackRate.toFixed(1) + "x";

      // 描画
      panel.innerHTML = "";
      cues.forEach((c, i) => {{
        const span = document.createElement("span");
        span.className = "word";
        span.textContent = c.text;
        span.dataset.i = i;
        span.onclick = () => {{
          player.currentTime = Math.max(0, Number(c.start) + 0.01);
          player.play();
          setActive(i);
        }};
        panel.appendChild(span);
      }});

      function setActive(i) {{
        document.querySelectorAll(".word").forEach(el => el.classList.remove("active"));
        const target = document.querySelector(`.word[data-i="${{i}}"]`);
        if (target) target.classList.add("active");
      }}

      // 速くなるよう二分探索（cuesはstart昇順の想定）
      function findIndex(t) {{
        let lo = 0, hi = cues.length - 1;
        while (lo <= hi) {{
          const mid = (lo + hi) >> 1;
          const c = cues[mid];
          if (t < c.start) hi = mid - 1;
          else if (t >= c.end) lo = mid + 1;
          else return mid;
        }}
        // どれにも入らないときは直前を返す（自然な見た目）
        return Math.max(0, Math.min(cues.length - 1, hi));
      }}

      player.addEventListener("timeupdate", () => {{
        const idx = findIndex(player.currentTime);
        setActive(idx);
      }});

      document.getElementById("play").onclick = () => player.play();
      document.getElementById("pause").onclick = () => player.pause();
      document.getElementById("stop").onclick = () => {{
        player.pause();
        player.currentTime = 0;
        setActive(-1);
      }};
    </script>
    """

    # Streamlit側にも再生とDL（st.audioはbytes対応）[4](https://huggingface.co/coqui/XTTS-v2)
    components.html(html, height=450, scrolling=True)
    st.download_button("⬇️ MP3ダウンロード", mp3_bytes, file_name="tts_ja.mp3", mime="audio/mpeg")
