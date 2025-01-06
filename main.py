import os
import json
import httpx
from dotenv import load_dotenv
from loguru import logger


load_dotenv()

airtable_access_token = os.getenv("AIRTABLE_ACCESS_TOKEN")
airtable_base_id = os.getenv("AIRTABLE_BASE_ID")
airtable_table_id = os.getenv("AIRTABLE_TABLE_ID")

client = httpx.Client(
    headers={
        # this is internal ID of an instagram backend app. It doesn't change often.
        "x-ig-app-id": "936619743392459",
        # use browser-like features
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.94 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept": "*/*",
    }
)


def get_airtable_records(offset=None):
    """
    Get all records from Airtable
    """

    request_url = f"https://api.airtable.com/v0/{airtable_base_id}/leads"
    if offset:
        request_url += f"?offset={offset}"

    response = httpx.get(
        request_url, headers={"Authorization": f"Bearer {airtable_access_token}"}
    )
    response_json = response.json()

    if response.status_code != 200:
        logger.error(f"Failed to get records: {response.status_code}")
        return []

    records = response_json["records"]

    # if offset is present, we need to make another request. We do this by
    # recursively calling this function
    if "offset" in response_json:
        return records + get_airtable_records(response_json["offset"])

    return records


def update_airtable_record(record_id: str, fields: dict):
    response = httpx.patch(
        f"https://api.airtable.com/v0/{airtable_base_id}/{airtable_table_id}/{record_id}",
        headers={"Authorization": f"Bearer {airtable_access_token}"},
        json={"fields": fields},
    )
    if response.status_code == 200:
        logger.debug(f"Successfully updated {record_id}")
    else:
        logger.error(
            f"Failed to update record {record_id} (status={response.status_code}, response={response.content})"
        )


def scrape_instagram_user(username: str):
    """Scrape Instagram user's data"""
    result = client.get(
        f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
    )
    if result.status_code == 404:
        return None

    data = json.loads(result.content)
    return data["data"]["user"]


def update_leads():
    # iterate over leads, if user is not found and status is NEW or CONTACTED or QUEUED,
    # change status to PAGE_DELETED
    logger.debug("Retrieving leads")
    leads = get_airtable_records()
    logger.info(f"Updating {len(leads)} leads")

    for lead in leads:
        lead_id = lead["id"]
        lead_name = lead["fields"]["name"]

        logger.info(f"Updating lead {lead_name}")

        ig_handle = lead["fields"]["instagram_handle"]
        # trim @ from the beginning if present
        ig_handle = ig_handle.lstrip("@")

        user = scrape_instagram_user(ig_handle)
        if user is None:
            logger.warning(f"User {ig_handle} not found, updating status to IG_DELETED")
            update_airtable_record(lead_id, {"status": "IG_DELETED"})
            continue

        follower_count = user["edge_followed_by"]["count"]
        following_count = user["edge_follow"]["count"]

        update_airtable_record(
            lead_id,
            {
                "instagram_handle": ig_handle,
                "instagram_link": f"https://www.instagram.com/{ig_handle}",
                "followers": follower_count,
                "following": following_count,
            },
        )


if __name__ == "__main__":
    update_leads()
