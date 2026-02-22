"""Quick test to understand OpenAI transcription API response format."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
from openai import OpenAI

client = OpenAI()
audio_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'demos', 'obama_romney_10min.mp3'))

output_file = os.path.join(os.path.dirname(__file__), '..', 'logs', 'api_test_output.txt')
os.makedirs(os.path.dirname(output_file), exist_ok=True)

with open(output_file, 'w', encoding='utf-8') as out:
    out.write(f"Audio: {audio_path}\n")
    out.write(f"Size: {os.path.getsize(audio_path) / 1024 / 1024:.1f} MB\n\n")
    
    # Test 1: verbose_json with gpt-4o-transcribe (known working)
    out.write("=" * 60 + "\n")
    out.write("TEST 1: gpt-4o-transcribe + verbose_json\n")
    out.write("=" * 60 + "\n")
    try:
        with open(audio_path, 'rb') as f:
            result = client.audio.transcriptions.create(
                model='gpt-4o-transcribe',
                file=f,
                response_format='verbose_json',
                timestamp_granularities=['segment'],
            )
        out.write(f"Type: {type(result)}\n")
        out.write(f"Text length: {len(result.text)}\n")
        out.write(f"Has segments: {hasattr(result, 'segments')}\n")
        if hasattr(result, 'segments') and result.segments:
            out.write(f"Num segments: {len(result.segments)}\n")
            for i, s in enumerate(result.segments[:5]):
                out.write(f"  Segment {i}: {s}\n")
        out.write(f"Text preview: {result.text[:500]}\n\n")
        
        # Dump full result structure
        if hasattr(result, 'model_dump'):
            d = result.model_dump()
            out.write(f"Keys: {list(d.keys())}\n")
            # Save segments to separate file
            if 'segments' in d and d['segments']:
                seg_file = os.path.join(os.path.dirname(output_file), 'test1_segments.json')
                with open(seg_file, 'w', encoding='utf-8') as sf:
                    json.dump(d['segments'][:10], sf, indent=2, ensure_ascii=False)
                out.write(f"First 10 segments saved to: {seg_file}\n")
    except Exception as e:
        out.write(f"ERROR: {e}\n")
    
    out.write("\n")
    
    # Test 2: Try gpt-4o-transcribe-diarize with verbose_json
    out.write("=" * 60 + "\n")
    out.write("TEST 2: gpt-4o-transcribe-diarize + verbose_json\n")
    out.write("=" * 60 + "\n")
    try:
        with open(audio_path, 'rb') as f:
            result2 = client.audio.transcriptions.create(
                model='gpt-4o-transcribe-diarize',
                file=f,
                response_format='verbose_json',
            )
        out.write(f"Type: {type(result2)}\n")
        out.write(f"Text length: {len(result2.text)}\n")
        
        # Check all attributes
        if hasattr(result2, 'model_dump'):
            d2 = result2.model_dump()
            out.write(f"Keys: {list(d2.keys())}\n")
            for k, v in d2.items():
                if k == 'text':
                    out.write(f"  {k}: {str(v)[:200]}...\n")
                elif isinstance(v, list):
                    out.write(f"  {k}: list of {len(v)} items\n")
                    if v:
                        out.write(f"    First item: {v[0]}\n")
                else:
                    out.write(f"  {k}: {v}\n")
            
            # Save full dump
            dump_file = os.path.join(os.path.dirname(output_file), 'test2_full_dump.json')
            with open(dump_file, 'w', encoding='utf-8') as df:
                json.dump(d2, df, indent=2, ensure_ascii=False, default=str)
            out.write(f"Full dump saved to: {dump_file}\n")
        else:
            out.write(f"Dir: {[a for a in dir(result2) if not a.startswith('_')]}\n")
    except Exception as e:
        out.write(f"ERROR: {e}\n")
        import traceback
        out.write(traceback.format_exc() + "\n")
    
    out.write("\n")
    
    # Test 3: Try gpt-4o-transcribe-diarize with diarized_json (raw HTTP)
    out.write("=" * 60 + "\n")
    out.write("TEST 3: gpt-4o-transcribe-diarize + diarized_json (raw)\n")
    out.write("=" * 60 + "\n")
    try:
        import httpx
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
        }
        with open(audio_path, 'rb') as f:
            files = {"file": ("obama_romney_10min.mp3", f, "audio/mpeg")}
            data = {
                "model": "gpt-4o-transcribe-diarize",
                "response_format": "diarized_json",
                "chunking_strategy": "auto",
            }
            resp = httpx.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers=headers,
                files=files,
                data=data,
                timeout=300,
            )
        out.write(f"Status: {resp.status_code}\n")
        out.write(f"Content-Type: {resp.headers.get('content-type')}\n")
        
        if resp.status_code == 200:
            body = resp.json()
            out.write(f"Response keys: {list(body.keys())}\n")
            for k, v in body.items():
                if isinstance(v, str) and len(v) > 200:
                    out.write(f"  {k}: {v[:200]}...\n")
                elif isinstance(v, list):
                    out.write(f"  {k}: list of {len(v)} items\n")
                    if v:
                        out.write(f"    First item keys: {list(v[0].keys()) if isinstance(v[0], dict) else type(v[0])}\n")
                        out.write(f"    First item: {json.dumps(v[0], ensure_ascii=False)[:300]}\n")
                        if len(v) > 1:
                            out.write(f"    Second item: {json.dumps(v[1], ensure_ascii=False)[:300]}\n")
                else:
                    out.write(f"  {k}: {v}\n")
            
            # Save full response
            resp_file = os.path.join(os.path.dirname(output_file), 'test3_diarized_response.json')
            with open(resp_file, 'w', encoding='utf-8') as rf:
                json.dump(body, rf, indent=2, ensure_ascii=False)
            out.write(f"Full response saved to: {resp_file}\n")
        else:
            out.write(f"Error body: {resp.text[:500]}\n")
    except Exception as e:
        out.write(f"ERROR: {e}\n")
        import traceback
        out.write(traceback.format_exc() + "\n")

print(f"Results written to: {output_file}")
