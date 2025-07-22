def get_headers():
    return {
        "accept": "application/json, text/plain, */*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9,si;q=0.8",
        "content-type": "application/json",
        "origin": "https://www.festo.com",
        "referer": "https://www.festo.com/gr/en/s/gripper-sizing/?accelerationAxis=Z_AXIS&accelerationValue=10&additionalFunctions=NONE&feather=NONE&grippingDirection=CLOSING&grippingJawsSurface=METAL&jawLength=20&mass=2.6&objectSurface=METAL&safetyFactor=2&stroke=10&utilizationDays=200&utilizationHours=8&utilizationMinutes=10",
        "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Mobile Safari/537.36",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        # The cookie string should be copied exactly from the browser (network tab)
        "cookie": "kameleoonVisitorCode=6xty4raqiknqu4hc; emos_jcvid=...; JHYSESSIONID=Y4-...; LastSite=gr-en-001"
    }