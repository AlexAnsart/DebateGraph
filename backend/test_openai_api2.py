"""Quick test to understand OpenAI transcription API response format - v2."""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

audio_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'demos', 'obama_romney_10min.mp3'))
output_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, 'api_test_output2.txt')

with open(output_file, 'w', encoding='utf-8') as out:
    out.write(f"Audio: {audio_path}\n")
    out.write(f"Size: {os.path.getsize(audio_path) / 1024 / 1024:.1f} MB\n\n")
    
    # ── Test 1: gpt-4o-transcribe with json format ──
    out.write("=" * 60 + "\n")
    out.write("TEST 1: gpt-4o-transcribe + json\n")
    out.write("=" * 60 + "\n")
    try:
        from openai import OpenAI
        client = OpenAI()
        t0 = time.time()
        with open(audio_path, 'rb') as f:
            result = client.audio.transcriptions.create(
                model='gpt-4o-transcribe',
                file=f,
                response_format='json',
            )
        elapsed = time.time() - t0
        out.write(f"Time: {elapsed:.1f}s\n")
        out.write(f"Type: {type(result)}\n")
        
        if hasattr(result, 'model_dump'):
            d = result.model_dump()
            out.write(f"Keys: {list(d.keys())}\n")
            for k, v in d.items():
                if isinstance(v, str) and len(v) > 300:
                    out.write(f"  {k}: ({len(v)} chars) {v[:300]}...\n")
                elif isinstance(v, list):
                    out.write(f"  {k}: list of {len(v)} items\n")
                    if v and len(v) > 0:
                        out.write(f"    First: {json.dumps(v[0], ensure_ascii=False)[:200]}\n")
                else:
                    out.write(f"  {k}: {v}\n")
        elif hasattr(result, 'text'):
            out.write(f"Text ({len(result.text)} chars): {result.text[:300]}...\n")
        else:
            out.write(f"Result: {str(result)[:500]}\n")
    except Exception as e:
        out.write(f"ERROR: {e}\n")
    out.write("\n")
    out.flush()
    
    # ── Test 2: Raw HTTP - gpt-4o-transcribe-diarize + json ──
    out.write("=" * 60 + "\n")
    out.write("TEST 2: gpt-4o-transcribe-diarize + json (raw HTTP)\n")
    out.write("=" * 60 + "\n")
    try:
        import httpx
        headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"}
        t0 = time.time()
        with open(audio_path, 'rb') as f:
            files = {"file": ("obama_romney_10min.mp3", f, "audio/mpeg")}
            data = {
                "model": "gpt-4o-transcribe-diarize",
                "response_format": "json",
            }
            resp = httpx.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers=headers,
                files=files,
                data=data,
                timeout=600,
            )
        elapsed = time.time() - t0
        out.write(f"Time: {elapsed:.1f}s\n")
        out.write(f"Status: {resp.status_code}\n")
        out.write(f"Content-Type: {resp.headers.get('content-type')}\n")
        
        if resp.status_code == 200:
            body = resp.json()
            out.write(f"Response keys: {list(body.keys())}\n")
            for k, v in body.items():
                if isinstance(v, str) and len(v) > 300:
                    out.write(f"  {k}: ({len(v)} chars) {v[:300]}...\n")
                elif isinstance(v, list):
                    out.write(f"  {k}: list of {len(v)} items\n")
                    if v:
                        first = v[0]
                        out.write(f"    First item type: {type(first).__name__}\n")
                        out.write(f"    First item: {json.dumps(first, ensure_ascii=False)[:300]}\n")
                        if len(v) > 1:
                            out.write(f"    Second item: {json.dumps(v[1], ensure_ascii=False)[:300]}\n")
                        if len(v) > 2:
                            out.write(f"    Third item: {json.dumps(v[2], ensure_ascii=False)[:300]}\n")
                elif isinstance(v, dict):
                    out.write(f"  {k}: dict with keys {list(v.keys())}\n")
                    out.write(f"    {json.dumps(v, ensure_ascii=False)[:300]}\n")
                else:
                    out.write(f"  {k}: {v}\n")
            
            # Save full response
            resp_file = os.path.join(output_dir, 'test2_diarize_json.json')
            with open(resp_file, 'w', encoding='utf-8') as rf:
                json.dump(body, rf, indent=2, ensure_ascii=False)
            out.write(f"\nFull response saved to: {resp_file}\n")
        else:
            out.write(f"Error: {resp.text[:500]}\n")
    except Exception as e:
        out.write(f"ERROR: {e}\n")
        import traceback
        out.write(traceback.format_exc() + "\n")
    out.write("\n")
    out.flush()
    
    # ── Test 3: Raw HTTP - gpt-4o-transcribe-diarize + diarized_json ──
    out.write("=" * 60 + "\n")
    out.write("TEST 3: gpt-4o-transcribe-diarize + diarized_json (raw HTTP)\n")
    out.write("=" * 60 + "\n")
    try:
        t0 = time.time()
        with open(audio_path, 'rb') as f:
            files = {"file": ("obama_romney_10min.mp3", f, "audio/mpeg")}
            data = {
                "model": "gpt-4o-transcribe-diarize",
                "response_format": "diarized_json",
            }
            resp = httpx.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers=headers,
                files=files,
                data=data,
                timeout=600,
            )
        elapsed = time.time() - t0
        out.write(f"Time: {elapsed:.1f}s\n")
        out.write(f"Status: {resp.status_code}\n")
        out.write(f"Content-Type: {resp.headers.get('content-type')}\n")
        
        if resp.status_code == 200:
            body = resp.json()
            out.write(f"Response keys: {list(body.keys())}\n")
            for k, v in body.items():
                if isinstance(v, str) and len(v) > 300:
                    out.write(f"  {k}: ({len(v)} chars) {v[:300]}...\n")
                elif isinstance(v, list):
                    out.write(f"  {k}: list of {len(v)} items\n")
                    if v:
                        first = v[0]
                        out.write(f"    First item type: {type(first).__name__}\n")
                        out.write(f"    First item: {json.dumps(first, ensure_ascii=False)[:300]}\n")
                        if len(v) > 1:
                            out.write(f"    Second item: {json.dumps(v[1], ensure_ascii=False)[:300]}\n")
                elif isinstance(v, dict):
                    out.write(f"  {k}: dict with keys {list(v.keys())}\n")
                else:
                    out.write(f"  {k}: {v}\n")
            
            resp_file = os.path.join(output_dir, 'test3_diarized_json.json')
            with open(resp_file, 'w', encoding='utf-8') as rf:
                json.dump(body, rf, indent=2, ensure_ascii=False)
            out.write(f"\nFull response saved to: {resp_file}\n")
        else:
            out.write(f"Error: {resp.text[:500]}\n")
    except Exception as e:
        out.write(f"ERROR: {e}\n")
        import traceback
        out.write(traceback.format_exc() + "\n")

print(f"Done! Results in: {output_file}")
