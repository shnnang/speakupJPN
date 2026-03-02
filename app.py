import streamlit as st
import streamlit.components.v1 as components
import asyncio
import edge_tts
from io import BytesIO

st.set_page_config(page_title="日本語読み上げ（無料B優先）", page_icon="🗣️", layout="centered")
st.title("🗣️ 日本語読み上げアプリ（無料：B優先 / A保険つき）")

st.caption("B: edge-tts（高品質MP3生成・APIキー不要） / A: ブラウザTTS（保険）")

text = st.text_area("文章を貼り付け", height=220, placeholder="ここに日本語の文章を貼り付け…")

with st.expander("⚙️ 音声設定（B: edge-tts）", expanded=True):
    voice = st.selectbox(
        "音声（おすすめ）",
        [
            "ja-JP-KeitaNeural",
            "ja-JP-NanamiNeural",
            "ja-JP-DaichiNeural",
            "ja-JP-AoiNeural",
        ],
        index=0,
        help="edge-tts は Microsoft Edge のオンラインTTSを使います（音声一覧は --list-voices で取得可能）。"
    )
    rate = st.slider("話速（%）", -50, 50, 0, 5)
    pitch = st.slider("音の高さ（Hz）", -50, 50, 0, 5)
    volume = st.slider("音量（%）", -50, 50, 0, 5)

def _prosody(rate, pitch, volume):
    # edge-tts の指定形式に整形（例: +10% / -5% / +5Hz）
    r = f"{rate:+d}%"
    v = f"{volume:+d}%"
    p = f"{pitch:+d}Hz"
    return r, v, p

async def synthesize_mp3_async(text: str, voice: str, rate: int, pitch: int, volume: int) -> bytes:
    r, v, p = _prosody(rate, pitch, volume)
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=r, pitch=p, volume=v)
    buf = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()

def synthesize_mp3(text: str, voice: str, rate: int, pitch: int, volume: int) -> bytes:
    # Streamlit内では asyncio.run が使えないケースがあるので安全側に寄せる
    try:
        return asyncio.run(synthesize_mp3_async(text, voice, rate, pitch, volume))
    except RuntimeError:
        # すでにイベントループが動いている環境向け
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(synthesize_mp3_async(text, voice, rate, pitch, volume))
        finally:
            loop.close()

st.divider()

colB, colA = st.columns([1, 1])

with colB:
    st.subheader("B) 高品質（edge-tts）でMP3生成")
    if st.button("🎧 生成して再生（B）", type="primary", use_container_width=True):
        if not text.strip():
            st.warning("文章を入力してね！")
        else:
            with st.spinner("音声を生成中…（数秒かかることがあります）"):
                try:
                    mp3_bytes = synthesize_mp3(text, voice, rate, pitch, volume)
                    st.success("生成できました！")
                    st.audio(mp3_bytes, format="audio/mp3")  # Streamlitのオーディオ再生 [7](https://docs.streamlit.io/develop/api-reference/media/st.audio)
                    st.download_button(
                        "⬇️ MP3をダウンロード",
                        data=mp3_bytes,
                        file_name="tts_ja.mp3",
                        mime="audio/mpeg",
                        use_container_width=True
                    )
                except Exception as e:
                    st.error("Bで失敗しました。A（ブラウザ読み上げ）を試してください。")
                    st.code(str(e))

with colA:
    st.subheader("A) ブラウザで直接読み上げ（保険）")
    st.caption("端末/ブラウザ依存。Bがダメな時の逃げ道。")
    # Web Speech API で読み上げ（前回の簡易版）
    html = f"""
    <div style="display:flex; gap:10px; align-items:center;">
      <button id="play" style="padding:8px 12px; border-radius:10px; border:1px solid #ddd; cursor:pointer;">▶️ 再生</button>
      <button id="stop" style="padding:8px 12px; border-radius:10px; border:1px solid #ddd; cursor:pointer;">⏹ 停止</button>
      <span id="status" style="font-size:12px; color:#666;"></span>
    </div>
    <script>
    const text = `{text.replace("`","\\`")}`;
    let utter = null;

    function setStatus(msg) {{
      document.getElementById("status").innerText = msg || "";
    }}

    function pickJaVoice() {{
      const voices = window.speechSynthesis.getVoices();
      return voices.find(v => (v.lang || "").toLowerCase().includes("ja")) || null;
    }}

    document.getElementById("play").onclick = () => {{
      if (!text || text.trim().length === 0) {{
        alert("文章を入力してください");
        return;
      }}
      window.speechSynthesis.cancel();
      utter = new SpeechSynthesisUtterance(text);
      const v = pickJaVoice();
      if (v) utter.voice = v;

      utter.onstart = () => setStatus("読み上げ中…");
      utter.onend = () => setStatus("完了");
      utter.onerror = () => setStatus("エラー");

      window.speechSynthesis.speak(utter);
    }};

    document.getElementById("stop").onclick = () => {{
      window.speechSynthesis.cancel();
      setStatus("停止しました");
    }};
    </script>
    """
    components.html(html, height=80)

st.info("Bの edge-tts は「Microsoft Edge のオンラインTTS」をPythonから利用する方式です（APIキー不要）。[1](https://pypi.org/project/edge-tts/)[2](https://github.com/rany2/edge-tts)")
``
