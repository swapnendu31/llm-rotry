// Mock data for LLM-rotry Static Dummy Mode
window.MOCK_KEYS = [
    {
        id: "mock-llm-1",
        key_type: "llm_call",
        provider: "OpenAI",
        account_name: "prod-gpt4o-primary",
        api_key: "sk-proj-aB9cDeFgHiJkLmNoPqRsTuVwXyZ1234567890",
        api_url: "https://api.openai.com/v1",
        status: "active",
        rpm: { rpm: 500, burst: 50 },
        rpd: { rpd: 10000, burst: 500 },
        rpmon: { rpm: 250000, burst: 5000 },
        tpm: { tpm: 300000, burst: 30000 },
        tpd: { tpd: 5000000, burst: 500000 },
        tpmon: { tpm: 120000000, burst: 5000000 },
        reg_date: "2026-03-01T10:00:00Z"
    },
    {
        id: "mock-llm-2",
        key_type: "llm_call",
        provider: "Anthropic",
        account_name: "claude-sonnet-fast",
        api_key: "sk-ant-api03-9KxL2mNpQrStUvWxYzAbCdEfGhIj1029384756",
        api_url: "https://api.anthropic.com/v1",
        status: "active",
        rpm: { rpm: 200, burst: 20 },
        rpd: { rpd: 5000, burst: 200 },
        rpmon: { rpm: 120000, burst: 2000 },
        tpm: { tpm: 160000, burst: 16000 },
        tpd: { tpd: 3000000, burst: 300000 },
        tpmon: { tpm: 75000000, burst: 3000000 },
        reg_date: "2026-03-02T11:30:00Z"
    },
    {
        id: "mock-llm-3",
        key_type: "llm_call",
        provider: "Google Gemini",
        account_name: "gemini-flash-tier2",
        api_key: "AIzaSyD-mockGoogleGeminiKey_XyZ9876543210",
        api_url: "https://generativelanguage.googleapis.com/v1beta",
        status: "inactive",
        rpm: { rpm: 1000, burst: 100 },
        rpd: { rpd: 20000, burst: 1000 },
        rpmon: { rpm: 500000, burst: 10000 },
        tpm: { tpm: 1000000, burst: 100000 },
        tpd: { tpd: 20000000, burst: 1000000 },
        tpmon: { tpm: 400000000, burst: 20000000 },
        reg_date: "2026-03-05T09:15:00Z"
    },
    {
        id: "mock-api-1",
        key_type: "api_call",
        provider: "Serper Search API",
        account_name: "search-agent-prod",
        api_key: "serper_live_98ab76cd54ef3210fedcba",
        api_url: "https://google.serper.dev/search",
        status: "active",
        rpm: { rpm: 60, burst: 10 },
        rpd: { rpd: 2500, burst: 100 },
        rpmon: { rpm: 60000, burst: 1000 },
        // Notice: NO TPM, TPD, or TPMon for api_call
        reg_date: "2026-03-07T14:20:00Z"
    },
    {
        id: "mock-api-2",
        key_type: "api_call",
        provider: "Tavily Web API",
        account_name: "research-tavily-backup",
        api_key: "tvly-prod-a9b8c7d6e5f4g3h2i1j0",
        api_url: "https://api.tavily.com/v1",
        status: "active",
        rpm: { rpm: 100, burst: 15 },
        rpd: { rpd: 4000, burst: 200 },
        rpmon: { rpm: 90000, burst: 2000 },
        // Notice: NO TPM, TPD, or TPMon for api_call
        reg_date: "2026-03-08T16:45:00Z"
    },
    {
        id: "mock-api-3",
        key_type: "api_call",
        provider: "WeatherAPI",
        account_name: "geocoding-weather-key",
        api_key: "wapi_4567890abcdef1234567890",
        api_url: "https://api.weatherapi.com/v1",
        status: "suspended",
        rpm: { rpm: 30, burst: 5 },
        rpd: { rpd: 1000, burst: 50 },
        rpmon: { rpm: 25000, burst: 500 },
        reg_date: "2026-03-09T08:00:00Z"
    }
];
