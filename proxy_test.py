import requests
import warnings
warnings.filterwarnings("ignore")

try:
    proxy_list = requests.get('https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=IN&ssl=all&anonymity=all').text.strip().split('\r\n')
    print(f"Found {len(proxy_list)} Indian proxies.")
    for p in proxy_list[:50]:
        if not p: continue
        try:
            r = requests.get('https://tnebsldc.org/reports1/peakdet.pdf', proxies={'http': 'http://'+p, 'https': 'http://'+p}, timeout=5, verify=False)
            if r.status_code == 200:
                print("SUCCESS with", p)
                break
            else:
                print("Failed with status:", r.status_code)
        except Exception as e:
            print("Timeout or error with", p)
except Exception as e:
    print("Error fetching proxies", e)
