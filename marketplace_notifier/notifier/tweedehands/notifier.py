import logging
from typing import List, Optional

from marketplace_notifier.notifier.models import IListingInfo, ListingLocation
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
            listing = api_models.Listing(**raw_listing)
            if not listing.is_ad():
                seller_url = str(
                    TweedehandsListingInfo.BASE_URL) + "/u/" + listing.seller_information.seller_name.lower().replace(
                    ".",
                    "-").replace(
                    " ", "-").replace("'", "-").replace("é", "e") + "/" + str(
                    listing.seller_information.seller_id)

                # TODO: add screenshot dependency
                # https://github.com/GoddeerisEdouard/ListingScreenshotter
                parsed_non_ad_tweedehands_listings.append(
                    TweedehandsListingInfo(id=listing.item_id,
                                           title=listing.title,
                                           price_info=listing.price_info,
                                           description=listing.description,
                                           screenshot_path=None,
                                           posted_date=listing.date,
                                           seller_url=seller_url,
                                           specified_location=ListingLocation(cityName=listing.location.city_name,
                                                                              countryName=listing.location.country_name,
                                                                              distanceMeters=listing.location.distance_meters),
                                           vip_url=listing.vip_url,
                                           thumbnail_url=listing.pictures[0].large_url if listing.pictures else None))

        return parsed_non_ad_tweedehands_listings
