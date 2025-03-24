import logging
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import ValidationError

from marketplace_notifier.notifier.models import ListingLocation
from marketplace_notifier.notifier.notifier import INotifier
from marketplace_notifier.notifier.tweedehands import api_models
from marketplace_notifier.notifier.tweedehands.return_models import TweedehandsListingInfo


class TweedehandsNotifier(INotifier):

    @property
    def marketplace(self) -> str:
        return "TWEEDEHANDS"

    def _parse_non_ad_listings(self, raw_listings_response) -> List[Optional[TweedehandsListingInfo]]:
        """
        helper method
        :param raw_listings_response: expected raw data format
         {...,
         "listings": [...],
         ...
         }
        :return: parsed List of non-ad IListingInfo objects
        """
        if len(raw_listings_response["listings"]) == 0:
            logging.debug("No listings (not even ads) found")
            return []

        # only return listings which aren't ads
        parsed_non_ad_tweedehands_listings = []
        for raw_listing in raw_listings_response["listings"]:
            try:
                listing = api_models.Listing(**raw_listing)
            except ValidationError as e:
                logging.error(f"Validation error while parsing listing\n{e}")
                continue
            except Exception as e:
                logging.error(f"Unexpected error while parsing listing\n{e}")
                continue

            if listing.is_ad():
                continue

            seller_url = str(
                TweedehandsListingInfo.BASE_URL) + "/u/" + listing.seller_information.seller_name.lower().replace(
                ".",
                "-").replace(
                " ", "-").replace("'", "-").replace("é", "e") + "/" + str(
                listing.seller_information.seller_id)

            # parse Literal dates
            if type(listing.date) is str:
                # NOTE: these dates will all have the time from fetching, not the actual time the listing got posted
                if listing.date == "Vandaag":
                    listing.date = datetime.now()
                elif listing.date == "Gisteren":
                    listing.date = datetime.now() - timedelta(days=1)
                elif listing.date == "Eergisteren":
                    listing.date = datetime.now() - timedelta(days=2)

            # we might also have to handle when the date is None

            # ALTERNATIVE:
            # if parsed_listing_info.date is None or type(parsed_listing_info.date) != datetime:
            #     logging.warning("came across a listing which doensn't have a date set: {parsed_listing_info.title}")
            #     - set date of object via set_posted_date()

            # TODO: add screenshot dependency
            # https://github.com/GoddeerisEdouard/ListingScreenshotter
            parsed_non_ad_tweedehands_listings.append(
                TweedehandsListingInfo(id=listing.item_id,
                                       title=listing.title,
                                       price_info=listing.price_info.human_readable_price,
                                       description=listing.description,
                                       screenshot_path=None,
                                       posted_date=listing.date,
                                       seller_url=seller_url,
                                       specified_location=ListingLocation(cityName=listing.location.city_name,
                                                                          countryName=listing.location.country_name,
                                                                          distanceMeters=listing.location.distance_meters),
                                       vip_url=listing.vip_url,
                                       thumbnail_url=str(listing.pictures[0].large_url) if listing.pictures else None))

        return parsed_non_ad_tweedehands_listings
