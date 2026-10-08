import asyncio
import json
import random
import time
import httpx

API_URL = "https://api.nendu.tech/proxy/nvidia/v1/chat/completions"
AUTH_KEY = "Lq9S2H0fdRGOk33DP+IaG8xTUXpesCwPyn38/C0t3unutbPz7iCZ3Gng"

HEADERS = {
    "X-Auth-Key": AUTH_KEY,
    "Content-Type": "application/json",
}

SAMPLE_PROMPTS = [
    "What is the capital of France?",
    "Give me a one-word synonym for fast.",
    "Name a primary color.",
    "What is 2 + 2?",
    "Which planet is closest to the Sun?",
    "Name a mammal that lays eggs.",
    "What gas do plants absorb?",
    "What is the freezing point of water in Celsius?",
    "Name the largest ocean on Earth.",
    "What is the chemical formula of water?",
    "What year did World War II end?",
    "Who painted the Mona Lisa?",
    "What is the square root of 64?",
    "What is the tallest mountain on Earth?",
    "Name the currency of Japan.",
    "What is the speed of light?",
    "Who wrote Hamlet?",
    "What is the smallest prime number?",
    "How many continents are there?",
    "What is the boiling point of water in Celsius?",
]


def create_payload(req_id: int, enable_thinking: bool) -> dict:
    prompt = random.choice(SAMPLE_PROMPTS)
    return {
        "model": "nvidia/nemotron-3.5-lightning-30b-a3b",
        "messages": [
            {
                "role": "user",
                "content": f"[Req #{req_id}] {prompt} Answer in under 10 words.",
            }
        ],
        "max_tokens": 128,
        "chat_template_kwargs": {
            "enable_thinking": enable_thinking,
        },
    }


async def send_single_req(client: httpx.AsyncClient, req_id: int, enable_thinking: bool) -> dict:
    payload = create_payload(req_id, enable_thinking)
    start = time.time()
    try:
        resp = await client.post(API_URL, headers=HEADERS, json=payload, timeout=120.0)
        elapsed = round(time.time() - start, 2)
        try:
            data = resp.json()
        except Exception:
            data = resp.text

        is_success = resp.status_code == 200
        error_source = None
        if not is_success:
            if resp.status_code == 429:
                text = str(data)
                if "exhausted or in cooldown" in text:
                    error_source = "Rotator 429 (Redis quota enforced: all keys exhausted)"
                else:
                    error_source = "Upstream NVIDIA 429"
            elif resp.status_code in (502, 503, 504):
                error_source = f"Gateway / Upstream failure ({resp.status_code})"
            else:
                error_source = f"HTTP {resp.status_code}"

        return {
            "id": req_id,
            "enable_thinking": enable_thinking,
            "status_code": resp.status_code,
            "latency": elapsed,
            "success": is_success,
            "error_source": error_source,
            "raw_response": data,
        }
    except Exception as e:
        elapsed = round(time.time() - start, 2)
        return {
            "id": req_id,
            "enable_thinking": enable_thinking,
            "status_code": 0,
            "latency": elapsed,
            "success": False,
            "error_source": f"Client Exception: {str(e)}",
            "raw_response": None,
        }


async def run_100_test():
    total_reqs = 100
    burst_size = 5
    num_batches = total_reqs // burst_size  # 20 batches
    # 20 batches across ~58 seconds => ~2.9s per batch
    batch_interval = 2.9

    print("=" * 65)
    print(f"🚀 RUNNING 100 REQS IN 1 MINUTE (5 CALLS/SEC BURSTS)")
    print(f"Total: {total_reqs} reqs | Batches: {num_batches} x {burst_size} calls | Target: ~60s")
    print(f"Configured Pool Capacity: 35 + 40 = 75 RPM")
    print("=" * 65)

    all_tasks = []
    start_time = time.time()

    async def log_wrapper(client, req_id, enable_thinking):
        res = await send_single_req(client, req_id, enable_thinking)
        icon = "✅" if res["success"] else "⚠️" if res["status_code"] == 429 else "❌"
        thk = "thinking=ON " if enable_thinking else "thinking=OFF"
        err = f" -> {res['error_source']}" if not res["success"] else ""
        print(f"[{res['id']:03d}/100] {icon} HTTP {res['status_code']} | {thk} | {res['latency']}s{err}")
        return res

    async with httpx.AsyncClient() as client:
        req_counter = 1
        for batch_idx in range(1, num_batches + 1):
            batch_start = time.time()
            batch_tasks = []

            print(f"\n--- Batch {batch_idx:02d}/{num_batches:02d}: Dispatched 5 concurrent calls ---")
            for _ in range(burst_size):
                enable_thinking = (req_counter % 2 == 1)
                t = asyncio.create_task(log_wrapper(client, req_counter, enable_thinking))
                batch_tasks.append(t)
                all_tasks.append(t)
                req_counter += 1

            elapsed_in_batch = time.time() - batch_start
            sleep_time = max(0.0, batch_interval - elapsed_in_batch)
            if batch_idx < num_batches:
                await asyncio.sleep(sleep_time)

        print("\nAll 100 requests dispatched. Awaiting any in-flight responses...")
        results = await asyncio.gather(*all_tasks)

    total_time = round(time.time() - start_time, 2)

    # Analytics
    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count
    success_rate = (success_count / len(results)) * 100

    latencies = [r["latency"] for r in results if r["success"]]
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0

    thinking_on_lat = [r["latency"] for r in results if r["success"] and r["enable_thinking"]]
    thinking_off_lat = [r["latency"] for r in results if r["success"] and not r["enable_thinking"]]

    avg_on = round(sum(thinking_on_lat) / len(thinking_on_lat), 2) if thinking_on_lat else 0
    avg_off = round(sum(thinking_off_lat) / len(thinking_off_lat), 2) if thinking_off_lat else 0

    # Group errors
    error_summary = {}
    for r in results:
        if not r["success"]:
            src = r["error_source"]
            error_summary[src] = error_summary.get(src, 0) + 1

    print("\n" + "=" * 65)
    print("📊 100 CALLS TEST RESULTS SUMMARY")
    print("=" * 65)
    print(f"Total Requests: {len(results)}")
    print(f"Total Duration: {total_time}s")
    print(f"Successful (HTTP 200): {success_count} ({success_rate:.1f}%)")
    print(f"Failed / Rate-Limited: {fail_count}")
    print(f"Average Latency (Overall 200s): {avg_latency}s")
    print(f"Average Latency (Thinking ON): {avg_on}s")
    print(f"Average Latency (Thinking OFF): {avg_off}s")

    if error_summary:
        print("\n🔍 Breakdown of Non-200 Responses:")
        for err, count in error_summary.items():
            print(f"  - {err}: {count} requests")
    else:
        print("\n🎉 All 100 requests returned HTTP 200!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_100_test())
