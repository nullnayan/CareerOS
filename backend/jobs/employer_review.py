"""All candidates retained; official career URL identification is not ATS proof."""
from jobs.registry import EMPLOYERS
from jobs.directory import company_directory

OFFICIAL = {
    "Amazon": "https://www.amazon.jobs/", "Microsoft": "https://careers.microsoft.com/",
    "Google": "https://www.google.com/about/careers/applications/", "Adobe": "https://careers.adobe.com/",
    "Salesforce": "https://www.salesforce.com/company/careers/jobs/", "Oracle": "https://careers.oracle.com/",
    "SAP": "https://jobs.sap.com/", "IBM": "https://www.ibm.com/careers/", "Zoho": "https://www.zoho.com/careers/",
    "PhonePe": "https://www.phonepe.com/careers/job-openings/", "Flipkart": "https://www.flipkartcareers.com/",
    "TCS": "https://www.tcs.com/careers/india", "Infosys": "https://www.infosys.com/careers/apply.html",
    "Wipro": "https://careers.wipro.com/", "HCLTech": "https://careers.hcltech.com/",
    "Accenture": "https://www.accenture.com/in-en/careers", "Cognizant": "https://careers.cognizant.com/",
    "Capgemini": "https://jobs.capgemini.com/", "JPMorgan Chase": "https://www.jpmorganchase.com/careers/explore-opportunities",
    "Goldman Sachs": "https://www.goldmansachs.com/careers/", "Morgan Stanley": "https://www.morganstanley.com/careers/career-opportunities-search/",
    "Postman": "https://www.postman.com/company/careers/open-positions/", "Twilio": "https://www.twilio.com/en-us/careers",
    "CRED": "https://careers.cred.club/", "Netflix": "https://www.jobs.netflix.com/", "Atlan": "https://atlan.com/careers/",
    "Linear": "https://linear.app/careers", "Deel": "https://www.deel.com/careers/",
    "NVIDIA": "https://www.nvidia.com/en-us/about-nvidia/careers/", "Mastercard": "https://careers.mastercard.com/",
    "Dell": "https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/careers/jobs",
    "Target": "https://corporate.target.com/careers", "Zepto": "https://www.zepto.com/s/careers", "Groww": "https://groww.in/careers",
    "Walmart": "https://careers.walmart.com/", "Juspay": "https://juspay.io/careers", "ServiceNow": "https://careers.servicenow.com/jobs/",
    "Cisco": "https://careers.cisco.com/", "PayPal": "https://careers.pypl.com/", "Thoughtworks": "https://www.thoughtworks.com/careers/jobs",
    "HPE": "https://careers.hpe.com/", "Deloitte": "https://www.deloitte.com/global/en/careers/job-search.html", "Tekion": "https://tekion.com/careers",
}


def employer_reviews():
    directory = company_directory()
    aliases = {"Razorpay": "Razorpay Software Private Limited", "Microsoft": "Microsoft AI"}
    rows = []
    for name in EMPLOYERS:
        boards = [board for board in directory if board["company"] == aliases.get(name, name)]
        url = OFFICIAL.get(name) or (boards[0]["url"] if boards else None)
        status = "board_mapping_reviewed" if boards else "official_careers_identified" if url else "mapping_required"
        prerequisite = "Connect a reviewed company board explicitly; setup does not start discovery." if boards else "Verify the current official ATS/site or obtain an employer-published feed before connecting."
        if name in {"PhonePe", "Postman"}: prerequisite += " Old Greenhouse slug returned 404; no old slug reused."
        if name == "Microsoft": prerequisite += " Mapping covers Microsoft AI only."
        if name == "Meesho": prerequisite += " Prior timeout excludes this board from default setup."
        rows.append({"company": name, "official_url": url, "mapping_status": status, "boards": boards,
                     "reviewed_at": "2026-11-02", "required_input": prerequisite,
                     "live_health": "see connection; no new collector probe"})
    return rows
