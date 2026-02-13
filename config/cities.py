"""config/cities.py — US states top 3 cities + categories."""
US_STATES_CITIES = {
    "Alabama":["Birmingham","Montgomery","Huntsville"],"Alaska":["Anchorage","Fairbanks","Juneau"],
    "Arizona":["Phoenix","Tucson","Mesa"],"Arkansas":["Little Rock","Fort Smith","Fayetteville"],
    "California":["Los Angeles","San Diego","San Jose"],"Colorado":["Denver","Colorado Springs","Aurora"],
    "Connecticut":["Bridgeport","New Haven","Hartford"],"Delaware":["Wilmington","Dover","Newark"],
    "Florida":["Jacksonville","Miami","Tampa"],"Georgia":["Atlanta","Augusta","Columbus"],
    "Hawaii":["Honolulu","Pearl City","Hilo"],"Idaho":["Boise","Meridian","Nampa"],
    "Illinois":["Chicago","Aurora","Joliet"],"Indiana":["Indianapolis","Fort Wayne","Evansville"],
    "Iowa":["Des Moines","Cedar Rapids","Davenport"],"Kansas":["Wichita","Overland Park","Kansas City"],
    "Kentucky":["Louisville","Lexington","Bowling Green"],"Louisiana":["New Orleans","Baton Rouge","Shreveport"],
    "Maine":["Portland","Lewiston","Bangor"],"Maryland":["Baltimore","Frederick","Rockville"],
    "Massachusetts":["Boston","Worcester","Springfield"],"Michigan":["Detroit","Grand Rapids","Warren"],
    "Minnesota":["Minneapolis","Saint Paul","Rochester"],"Mississippi":["Jackson","Gulfport","Southaven"],
    "Missouri":["Kansas City","Saint Louis","Springfield"],"Montana":["Billings","Missoula","Great Falls"],
    "Nebraska":["Omaha","Lincoln","Bellevue"],"Nevada":["Las Vegas","Henderson","Reno"],
    "New Hampshire":["Manchester","Nashua","Concord"],"New Jersey":["Newark","Jersey City","Paterson"],
    "New Mexico":["Albuquerque","Las Cruces","Rio Rancho"],"New York":["New York City","Buffalo","Rochester"],
    "North Carolina":["Charlotte","Raleigh","Greensboro"],"North Dakota":["Fargo","Bismarck","Grand Forks"],
    "Ohio":["Columbus","Cleveland","Cincinnati"],"Oklahoma":["Oklahoma City","Tulsa","Norman"],
    "Oregon":["Portland","Salem","Eugene"],"Pennsylvania":["Philadelphia","Pittsburgh","Allentown"],
    "Rhode Island":["Providence","Warwick","Cranston"],"South Carolina":["Charleston","Columbia","North Charleston"],
    "South Dakota":["Sioux Falls","Rapid City","Aberdeen"],"Tennessee":["Nashville","Memphis","Knoxville"],
    "Texas":["Houston","San Antonio","Dallas"],"Utah":["Salt Lake City","West Valley City","Provo"],
    "Vermont":["Burlington","South Burlington","Rutland"],"Virginia":["Virginia Beach","Norfolk","Chesapeake"],
    "Washington":["Seattle","Spokane","Tacoma"],"West Virginia":["Charleston","Huntington","Morgantown"],
    "Wisconsin":["Milwaukee","Madison","Green Bay"],"Wyoming":["Cheyenne","Casper","Laramie"],
}
CATEGORIES = ["cinema","gaming","culture_entertainment"]
CATEGORY_LABELS = {"cinema":"Cinema / Movie Reviews","gaming":"Gaming / Video Games","culture_entertainment":"Culture & Entertainment"}
CATEGORY_SEARCH_TERMS = {
    "cinema":["movie review","film review","film critic","cinema","movie commentary","film analysis"],
    "gaming":["gaming","gamer","gameplay","let's play","game review","video game","streamer"],
    "culture_entertainment":["vlog","lifestyle","culture","entertainment","comedy","podcast","pop culture"],
}
