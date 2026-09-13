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
        rpm: 500,
        rpd: 10000,
        rpmon: 250000,
        tpm: 300000,
        tpd: 5000000,
        tpmon: 120000000,
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
        rpm: 200,
        rpd: 5000,
        rpmon: 120000,
        tpm: 160000,
        tpd: 3000000,
        tpmon: 75000000,
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
        rpm: 1000,
        rpd: 20000,
        rpmon: 500000,
        tpm: 1000000,
        tpd: 20000000,
        tpmon: 400000000,
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
        rpm: 60,
        rpd: 2500,
        rpmon: 60000,
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
        rpm: 100,
        rpd: 4000,
        rpmon: 90000,
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
        rpm: 30,
        rpd: 1000,
        rpmon: 25000,
        reg_date: "2026-03-09T08:00:00Z"
    }
];
