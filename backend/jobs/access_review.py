"""Dated primary-source assessment; availability is never inferred from research.

These are access findings, not executable collectors or successful live probes.
"""
DATE = "2026-11-02"
# name: primary URL, precise remaining input, finding
REVIEWS = {
    "LinkedIn": ("https://www.linkedin.com/legal/user-agreement", "LinkedIn-authorized candidate listing export/collection agreement", "Automated scraping is restricted by the user agreement. Reviewed supplied content only."),
    "Naukri.com": ("https://www.naukri.com/termsconditions", "Permitted Naukri export/feed contract and schema", "Terms route was robots-blocked to the research browser; collection permission remains unresolved."),
    "Unstop": ("https://unstop.com/jobs", "Unstop-supported public jobs export and access conditions", "Public jobs exist; no supported unattended export contract was established."),
    "Internshala": ("https://internshala.com/terms", "Internshala permission for extraction/export", "Prior review recorded extraction restrictions; current terms route is robots-blocked. No collector enabled."),
    "Wellfound": ("https://wellfound.com/terms", "Wellfound-authorized opportunity export", "Talent terms restrict harvesting/copying. Candidate login and recruiter MCP are not listing access."),
    "Indeed": ("https://docs.indeed.com/", "Indeed-approved candidate search/feed agreement", "Published partner integrations concern employer posting/applications; an unrestricted candidate catalogue was not established."),
    "Foundit": ("https://www.foundit.in/", "Foundit-supported free listing feed/export and reuse conditions", "Public job search is identifiable; an approved ongoing free machine feed was not established."),
    "Cutshort": ("https://cutshort.io/jobs", "Cutshort-supported listing feed/export and access conditions", "A job search page is not a verified collection API; unattended access remains unverified."),
    "Instahyre": ("https://help.instahyre.com/en/article/get-started-with-ats-integration-14s0ijg/", "Separate permitted free candidate listing export", "Official ATS integration needs employer admin access and a yearly subscription. It exports candidates, not a free candidate job catalogue."),
    "Hirist.tech": ("https://recruit.hirist.tech/terms-condition", "Hirist-supported job export and permission", "Recruiter terms identify the service; no free candidate collection contract was established."),
    "AICTE Internship Portal": ("https://internship.aicte-india.org/", "AICTE-published internship feed/export URL and reuse terms", "Government portal identification does not establish a supported open API."),
    "National Career Service": ("https://www.ncs.gov.in/Documents/User%20Manual_External%20Partner.pdf", "NCS partner-approved vacancy export route, schema and scope", "External partner registration and jobseeker browsing are different from a vacancy export agreement."),
    "Glassdoor": ("https://www.glassdoor.com/crs/api/glassdoor-public-api-terms.pdf", "Current approved API/export access and nonexpiring free terms", "Published API terms are not an issued connection or evidence of current free access."),
    "ZipRecruiter": ("https://www.ziprecruiter.com/partner/documentation/mcp-connector/", "Supported CareerOS MCP transport endpoint and data-use contract", "Official search MCP exists: US/CA, five results per call, limited offsets, no end-user OAuth. Docs direct users to app directories but do not supply a backend transport URL. Not integrated."),
    "Bayt": ("https://www.bayt.com/en/pages/terms/", "Bayt-authorized listing export/feed", "Terms describe extraction monitoring and recruitment products; no approved free search export established."),
    "BDJobs": ("https://bdjobs.com/tos/", "BDJobs-supported vacancy export and access conditions", "Bangladesh source; service terms do not establish a free catalogue export."),
    "HelloWork": ("https://recruteur.hellowork.com/fr/page/nos-partenaires-ats.html", "HelloWork-approved listing export; France coverage acceptable", "ATS partner docs describe job distribution/application delivery, not a free candidate catalogue."),
    "FirstNaukri": ("https://www.firstnaukri.com/", "FirstNaukri-published listing feed/export and permission", "No supported ongoing free unattended listing contract established."),
    "Cuvette": ("https://cuvette.tech/", "Cuvette-supported listing export/feed and permission", "No supported ongoing free unattended listing contract established."),
    "YC Work at a Startup": ("https://www.workatastartup.com/", "YC-supported public job export and reuse conditions", "YC company/job pages do not establish an unrestricted candidate catalogue API."),
    "HackerEarth": ("https://www.hackerearth.com/challenges/", "Permitted hiring-challenge feed including deadlines and employer links", "A coding/evaluation API is not a hiring-challenge catalogue. No such feed established."),
    "HackerRank": ("https://www.hackerrank.com/work/mcp/docs/", "Separate approved candidate hiring-event/job feed", "Official MCP serves assessments, candidates and employer workflow; it is not a candidate job-search tool."),
    "CodeChef": ("https://www.codechef.com/", "CodeChef-supported hiring-event export with job provenance", "Contest availability is not evidence of a hiring/job API; no such route established."),
    "JobsNet": ("https://jobsnet.in/about", "Confirm intended JobsNet service; publisher-approved structured feed", "jobsnet.in identifies an Indian early-career publisher and claims JobPosting markup; intended identity and reuse permission remain unresolved."),
    "YoHire": ("https://yohire.in/about", "Publisher-approved YoHire feed and reuse terms", "Indian off-campus publisher identified; no permitted machine export contract established."),
    "FreshersBridge": ("https://www.freshersbridge.in/", "Publisher-approved structured job feed and reuse agreement", "Official Indian fresher job publisher identified in primary results; public listings do not establish export or extraction permission."),
    "JoinSaarthi": ("https://joinsaarthi.com/explore", "Saarthi-supported drive/job export with permission", "Official fresher jobs/placement service identified; no public export contract established."),
    "Preplaced": ("https://www.preplaced.in/legal", "Published job feed separate from mentoring products", "Mentoring service and legal page identified; no supported vacancy catalogue established."),
    "TalentBattle": ("https://talentbattle.in/terms-privacy", "Permitted publisher feed with official employer links/deadlines", "Placement/training and job-update pages exist; no reusable free export contract established."),
    "PrepInsta": ("https://prepinsta.com/terms-and-conditions/", "Permitted job-update feed with original employer provenance", "Training/content terms and job announcements do not establish automated collection permission."),
    "FreshersNow": ("https://www.freshersnow.com/terms-conditions/", "Publisher's express permission or use original employer sources", "Terms restrict copying/downloading without written permission; no unattended collector enabled."),
    "Workday": ("https://www.workday.com/en-us/company/careers.html", "Exact external employer career-site root and employer public-access review", "Bounded CXS career-site adapter fixture-tested, not an official supported Workday API. No employer enabled or live collector verification claimed."),
    "Oracle Recruiting": ("https://docs.oracle.com/en/cloud/saas/human-resources/farws/op-recruitingcejobrequisitions-get.html", "Employer-published public XML/JSON/JobPosting feed URL", "Candidate-experience API documentation does not establish universal tenant access; only explicit published feeds are supported here."),
    "Taleo": ("https://docs.oracle.com/en/cloud/saas/taleo-enterprise/21d/otcug/c-rssfeature.html", "Exact public RSS URL generated by the employer career section", "Employer must enable RSS; maximum ten job excerpts, not exhaustive. Feed parser and scheduler route fixture-tested."),
    "SAP SuccessFactors": ("https://help.sap.com/docs/successfactors-recruiting/setting-up-and-maintaining-sap-successfactors-recruiting/command-center-feed-management", "Employer-published Command Center XML feed URL", "SAP documents employer-configured XML feeds. Tenant OData credentials are not needed for a public feed; no feed assumed."),
    "iCIMS": ("https://developer-community.icims.com/applications/applicant-tracking/job-portal", "Employer-published public feed or separately approved vendor connection", "Official Job Portal API examples require Basic authorization and customer/portal IDs. This implementation only consumes explicit public feeds."),
}
COMMUNITY_SITES = {"LinkedIn": "linkedin", "Naukri.com": "naukri", "Indeed": "indeed", "Glassdoor": "glassdoor",
                   "ZipRecruiter": "zip_recruiter", "Bayt": "bayt", "BDJobs": "bdjobs", "HelloWork": "hellowork"}


def assessment(name):
    if name not in REVIEWS: return {}
    url, needed, finding = REVIEWS[name]
    result = {"documentation_url": url, "checked_at": DATE, "conditions": finding,
              "required_prerequisite": needed, "research_status": "assessed_route" if url else "identity_unresolved"}
    if name in COMMUNITY_SITES:
        result.update(community_tool="JobSpy", community_site=COMMUNITY_SITES[name],
                      community_status="offline_export_import_tested; package_not_installed; no_live_collection",
                      community_documentation_url="https://github.com/speedyapply/JobSpy")
    if name in {"Workday", "Oracle Recruiting", "Taleo", "SAP SuccessFactors", "iCIMS"}:
        result.update(implementation="fixture_tested", health="never_checked", scope="employer_configured",
                      cost="ongoing_public_access_if_employer_publishes", polling_floor_seconds=3600,
                      description="feed-dependent; Taleo always excerpts", pagination="bounded checkpoints; no inferred closure")
    else: result.update(implementation="researching")
    return result
