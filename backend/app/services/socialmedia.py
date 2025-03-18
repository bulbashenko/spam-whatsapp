import requests
import json
from app.core.config import settings

class SocialMediaService:
    def __init__(self, *args, **kwargs):
        self.api_key = settings.SERPER_API_KEY="REMOVED"
        self.url = "https://google.serper.dev/search"

    def search_social_profiles(self, company_name):
        """
        Searches for social media profiles related to the company using Serper API.
        Returns a JSON with extracted social media links.
        """
        payload = json.dumps({"q": company_name})
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }

        response = requests.post(self.url, headers=headers, data=payload)
        data = response.json()

        profiles = {
            "company": company_name,
            "social_links": []
        }

        if "organic" in data:
            for result in data["organic"]:
                link = result.get("link")
                if link and any(site in link for site in ["linkedin.com", "twitter.com", "facebook.com", "instagram.com"]):
                    profiles["social_links"].append(link)

        return json.dumps(profiles, indent=4)

service = SocialMediaService()
profiles_json = service.search_social_profiles("Apple Inc")

print(profiles_json)
