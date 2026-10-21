"""Approved report wording: Assumptions, Special Assumptions, Property
Condition and Property Specification ("Valuation Report Text Inputs", Google
Doc, Oct 2026). Loaded into the text library by `dictionary.sync`; admins can
edit it afterwards in Admin.

Square brackets are blanks the valuer fills in for each job ("[date]",
"[client]"); a report can't be issued while one is left (apps.reports.issue).
Lines starting "- " print as bullet points.
"""

# The opening Assumptions and Special Assumptions paragraphs print in every
# report: they are in the report template (apps/reports/default_template).

ASSUMPTIONS = [
    ("Vacant and Furnished",
     "At the time of our inspection, the property was vacant and furnished. Our opinion of Market Value relates to "
     "the real property interest only and has been prepared on the basis of vacant possession. It excludes all "
     "furniture, furnishings and other moveable items present at the property, whether owned by the owner, an "
     "occupier or a third party.\n\n"
     "For the avoidance of doubt, our valuation includes fixtures and fittings that form part of the property, "
     "including built-in kitchen appliances (such as integrated ovens, hobs, extractor hoods, fridges, dishwashers "
     "and washing machines), fitted wardrobes and air-conditioning units, where present.\n\n"
     "Where comparable evidence relates to properties sold or let furnished, this has been taken into account in "
     "our analysis."),
    ("Multiple Properties on Single Plot",
     "The subject plot, [Plot No. XXX], accommodates two buildings: [Building Type XXXX] and [Building Type XXXX]. "
     "We understand that both buildings are held under a single title deed, and that the plot has not been "
     "subdivided or registered under a jointly owned property / strata scheme.\n\n"
     "We have valued the property as a whole, comprising the land and both buildings, on the basis that it would "
     "be sold as a single lot. We have assumed that both buildings are built in accordance with the relevant "
     "approvals and the permitted parameters for the plot, and that neither building could be sold or transferred "
     "separately without subdivision or strata registration."),
    ("Unofficial Source of Information",
     "In preparing this valuation, we have relied on information provided by [the client / the client’s "
     "representative / the developer] contained in the following documents: [Document Type XXX]. These documents "
     "are not official government records, issued by the Land Department or relevant authority. We have not been "
     "able to verify this information against official records, and we have assumed that it is accurate, complete "
     "and current as at the valuation date.\n\n"
     "In particular, we have relied on these documents for [the property’s ownership / unit number / built-up "
     "area / plot area / purchase price / handover status / other]. If any of this information is found to be "
     "inaccurate or incomplete, or if official records differ from it, our opinion of value may need to be "
     "revised. We recommend that the information be verified against the relevant official records before any "
     "reliance is placed on this report, and we reserve the right to amend our valuation on receipt of such "
     "records."),
    ("Combined Units with Separate Title Deeds",
     "The property comprises [number] [office / retail] units, [Unit Nos. XXX, XXX], within [Building Name], each "
     "held under a separate title deed. At the time of our inspection, the units had been physically combined and "
     "were being used as a single [office / retail] premises.\n\n"
     "As each unit is held under its own title deed and may be sold separately, we have valued each unit "
     "individually. The total value reported is the sum of the individual unit values and does not reflect any "
     "premium or discount that may apply if the units were sold together as a single lot. We have made no "
     "allowance for the cost of reinstating the units to their original separate layout. We have assumed that the "
     "works to combine the units were carried out with all necessary approvals from the developer and the "
     "relevant authorities."),
    ("Drive By/External Inspection",
     "We carried out an external inspection of the property from [the public highway / the building’s common "
     "areas] on [date]. We did not inspect the interior of the property. Our assessment of its internal layout, "
     "specification, condition and state of repair is based on [information provided by the client / the "
     "developer’s floor plans and brochure / our knowledge of comparable units in the building], and not on our "
     "own observation.\n\n"
     "A full inspection may reveal matters that would cause us to revise our opinion of value. Should such matters "
     "be made known, we reserve the right to make amendments to this report."),
    ("Desktop Valuation",
     "In accordance with the client’s instructions, and as agreed in our terms of engagement, this valuation has "
     "been prepared on a restricted basis.\n\n"
     "We have not inspected the property, either internally or externally. Our valuation is based entirely on "
     "information provided by [the client / the client’s representative] and on our own desktop research, "
     "including [title deed / affection plan / floor plans / photographs / DLD transaction data / online "
     "mapping].\n\n"
     "In preparing this valuation, we have assumed that:\n"
     "- The property is in a reasonable state of repair and condition, consistent with its age and with "
     "comparable properties in the vicinity;\n"
     "- Its accommodation, layout, specification and areas are as described in the information provided;\n"
     "- There are no defects, alterations, unauthorised works or other matters that a full internal inspection "
     "would have revealed and that would materially affect value; and\n"
     "- The property’s location, access and surroundings are as shown in the information and mapping we "
     "reviewed.\n\n"
     "A full inspection may reveal matters that would cause us to revise our opinion of value. Should such matters "
     "be made known, we reserve the right to make amendments to this report."),
    ("Exaggerated Built Up Area (BUA)",
     "The BUA provided by [source] is [xxxx] sq ft and the title deed area is [xxxx] sq ft. Based on our "
     "inspection, the documentation reviewed and our experience of comparable [units] in [community], which "
     "typically range from [xxxx] to [xxxx] sq ft, we consider the stated BUA to be overstated. This is likely due "
     "to [the inclusion of terraces / balconies / unapproved enclosures].\n\n"
     "We have therefore adopted an assessed BUA of [xxxx] sq ft. This is an estimate based on professional "
     "judgement; we have not undertaken a measured survey. Supporting evidence has been retained on our file, and "
     "this matter was raised with [client] on [date] before this report was issued. We reserve the right to "
     "revise our valuation should a measured survey or approved documentation confirm a different area."),
    ("Property affected by Flood",
     "[During our inspection we observed / We have been informed by [source] of] evidence that the property has "
     "been affected by flooding, including [water staining / damp / damaged finishes / repairs to xxxxx area].\n\n"
     "We are not qualified to assess structural, MEP or latent damage and have not undertaken a building or "
     "drainage survey. In our valuation we have [assumed that any damage has been fully and satisfactorily "
     "remediated / reflected the observed condition], and have considered the potential impact of flood history "
     "on market perception and buyer demand in [community]. This matter was raised with [client] on [date] prior "
     "to the issue of this report.\n\n"
     "We recommend a building condition survey by a suitably qualified surveyor prior to any transaction or "
     "lending decision, and reserve the right to revise our valuation should that survey reveal any further "
     "defects."),
    ("Industrial Cleaning and Repair Work Required",
     "We inspected the unit on [date]. The inspection was visual only and limited to accessible areas. We are not "
     "building surveyors and have not undertaken a building condition survey, structural survey or testing of the "
     "MEP services.\n\n"
     "At the date of our inspection, the unit was in [poor / below-average] condition and, in our opinion, "
     "requires industrial cleaning and repair works, including [damaged flooring / wall and ceiling repairs / "
     "damaged joinery / sanitary fittings / AC servicing / repainting]. Photographs of the observed condition "
     "have been retained on our file.\n\n"
     "Other than the defects noted above, we have assumed that there are no latent defects, structural issues or "
     "deficiencies in the building services. The condition of the unit was brought to the attention of [client] "
     "on [date] prior to the issue of this report.\n\n"
     "Should a building condition survey or contractor quotations reveal further defects or a materially "
     "different cost of works, we reserve the right to revise our valuation. We recommend that a building "
     "condition survey be undertaken by a suitably qualified surveyor prior to any transaction or lending "
     "decision."),
    ("Limited Access to the Property (Subject to Bank Approval)",
     "We inspected the property on [date]. Access was limited, and we were unable to inspect [the interior of the "
     "property / the following areas: xxxx] because [the tenant / occupier / owner declined access / the areas "
     "were locked / xxxx].\n\n"
     "[Our inspection was confined to an external inspection of the property and its surroundings.] For the "
     "areas not inspected, we have assumed that their condition, specification, layout and finishes are "
     "[consistent with the areas we were able to inspect / consistent with comparable units in xxxxx], that they "
     "are free from defects or unauthorised modifications, and that they comply with the approved plans.\n\n"
     "We have relied on [the title deed / floor plans / photographs / information provided by xxxx] in forming "
     "this assumption and have not verified it independently.\n\n"
     "This limitation was brought to the attention of [client] on [date], who instructed us to proceed on this "
     "basis prior to the issue of this report. Should a full inspection reveal any matters inconsistent with "
     "these assumptions, our valuation may be materially affected, and we reserve the right to revise it. We "
     "recommend that a full internal inspection be undertaken prior to any transaction or lending decision."),
    ("Satellite Imagery to Calculate BUA",
     "No floor plans, title deed area or other official documentation stating the BUA of the property were "
     "available to us. We have estimated the BUA at approximately [xxxxxx] sq ft using satellite imagery, by "
     "measuring the building footprint and applying [the number of floors observed during our inspection on "
     "[date]]. We have assumed that the upper floors are broadly consistent with the ground floor footprint and "
     "that our estimate is reasonably representative of the actual BUA. We have not undertaken a measured "
     "survey, and the actual area may differ. Given that the BUA is a key input to our valuation, our opinion of "
     "value is subject to [a higher degree of uncertainty than would normally apply]. We recommend that a "
     "measured survey be undertaken by a suitably qualified surveyor prior to any transaction or lending "
     "decision, and reserve the right to revise our valuation should the actual area differ."),
    ("Moisture Damage",
     "We inspected the property on [date]. Our inspection was visual only, and we are not qualified to determine "
     "the cause, extent or remediation of the issues noted. We observed evidence of moisture damage, including "
     "[damp patches / water staining / peeling paint / mould growth / blistered plaster / damaged skirting / "
     "xxxx], affecting [the master bathroom / ceiling of xxxx / external walls / xxxx].\n\n"
     "We have not undertaken moisture testing or a building condition survey, nor investigated the plumbing, "
     "waterproofing or drainage systems. Photographs of the observed damage have been retained on our file.\n\n"
     "Our opinion of Market Value reflects the current condition of the property and includes an allowance of "
     "approximately AED [xxxx] for investigation and remedial works. This allowance is our estimate, based on our "
     "market experience. We have not obtained contractor quotations, and the actual cost may differ. Apart from "
     "the damage noted above, we have assumed that there is no further concealed or latent damage, including to "
     "the structure, waterproofing or building services. This matter was brought to the attention of [client] on "
     "[date], prior to the issue of this report.\n\n"
     "We recommend that a building condition survey, including an investigation into the cause of the moisture, "
     "be undertaken by a suitably qualified surveyor prior to any transaction or lending decision. Should that "
     "investigation reveal more extensive damage or a materially different cost of remediation, we reserve the "
     "right to revise our valuation."),
    ("No Access to One or More Rooms",
     "We inspected the property on [date]. We were unable to access [the bedroom / storage room / xxxx] because "
     "[it was locked / the occupier declined access / xxxxx]. All other areas of the property were inspected.\n\n"
     "We have assumed that the condition, specification and finishes of the uninspected room are consistent with "
     "the rest of the property, that it is free from defects, damage or unauthorised modifications, and that its "
     "layout and size accord with [the floor plans provided / comparable units in xxxx]. We have not verified "
     "this independently.\n\n"
     "This limitation was brought to the attention of [client] on [date], who instructed us to proceed on this "
     "basis prior to the issue of this report. Should an inspection of the room reveal any matters inconsistent "
     "with these assumptions, our valuation may be affected and we reserve the right to revise it."),
    ("No Photographs allowed on Site",
     "We inspected the property on [date]. The tenant did not permit photographs to be taken during the "
     "inspection. The inspection was otherwise completed [in full / subject to the limitations set out in this "
     "report], and our observations of the property’s condition, specification and layout were recorded in "
     "written inspection notes, which have been retained on our file.\n\n"
     "As a result, this report does not include internal photographs of the property [and the photographs "
     "included are limited to the external elevations and surroundings].\n\n"
     "Our opinion of value is based on our observations during the inspection. We have assumed that the "
     "condition of the property has not materially changed since the date of our inspection.\n\n"
     "This restriction was brought to the attention of [client] on [date], who instructed us to proceed on this "
     "basis prior to the issue of this report."),
    ("Assumed NOC Obtained",
     "During our inspection on [date], we observed that the property has been modified from its original layout, "
     "including [extension / enclosed terrace / pergola / swimming pool / conversion of xxxxx / xxxxxx]. We "
     "understand that, within [community], such modifications typically require a No Objection Certificate (NOC) "
     "from [the master developer / community management] and approvals from [Dubai Municipality / Trakhees / DDA "
     "/ the relevant authority].\n\n"
     "We have not been provided with these NOCs or approvals and have not verified their existence with the "
     "relevant authorities. For the purposes of this valuation, we have assumed that all necessary NOCs, permits "
     "and approvals have been obtained, that the works have been completed in accordance with them, and that "
     "there are no outstanding fines, penalties or enforcement actions relating to the modifications. Our "
     "opinion of Market Value reflects the property as modified.\n\n"
     "Should this assumption prove incorrect, our valuation may be materially affected, including by any cost of "
     "reinstatement, fines or penalties, and we reserve the right to revise it. This matter was brought to the "
     "attention of [client] on [date], prior to the issue of this report. We recommend that copies of all "
     "relevant NOCs and approvals be obtained and verified prior to any transaction or lending decision."),
    ("Structural Damage",
     "We inspected the property on [date]. Our inspection was visual only. We are not structural engineers and "
     "are not qualified to assess the cause, extent, stability implications or remediation of structural "
     "defects. During our inspection we observed evidence of possible structural damage, including [cracking to "
     "xxxx walls / ceiling / slab / columns / beams, settlement, deflection, spalling concrete, exposed or "
     "corroded reinforcement, distorted door or window frames / xxxxx], affecting [location within the "
     "property]. We have not undertaken a structural survey or any testing. Photographs and notes of the observed "
     "damage have been retained on our file.\n\n"
     "Our opinion of Market Value reflects the property in its current condition, disregarding any costs for "
     "structural investigation and remedial works, and the likely impact of the observed damage on market "
     "perception and buyer demand.\n\n"
     "Because the extent and cause of the damage are unknown, our valuation is subject to a higher degree of "
     "uncertainty than would normally apply. Apart from the damage noted above, we have assumed that there are "
     "no further concealed or latent structural defects.\n\n"
     "We strongly recommend that a structural survey be undertaken by a suitably qualified structural engineer "
     "prior to any transaction or lending decision. Should that survey reveal more extensive damage, safety "
     "concerns or a materially different cost of remediation, we reserve the right to revise our valuation."),
    ("Title Deed Error",
     "We have been provided with a copy of the title deed for the subject property, dated [xxxx]. In our review "
     "we noted a discrepancy between the title deed and [our inspection / the documentation provided / DLD "
     "records] concerning [the unit number / plot number / building name / property type / area / usage / xxxx]. "
     "The title deed states [xxxx], whereas [our inspection / the documentation indicates] [xxxx]. We are not "
     "legal advisers and have not investigated the cause of this discrepancy.\n\n"
     "For the purposes of this valuation, we have assumed that the discrepancy is administrative in nature, that "
     "the property identified and inspected by us is the property to which the title deed relates, that the "
     "owner holds good and marketable title, and that the title deed can be rectified with the Dubai Land "
     "Department without material cost, delay or impact on the property’s legal status. Our valuation is based "
     "on [the details observed during our inspection / the corrected details].\n\n"
     "This matter was brought to the attention of [client] on [date], prior to the issue of this report. We "
     "recommend that the title deed be rectified with the Dubai Land Department, and the corrected title deed "
     "verified by the client’s legal advisers, prior to any transaction or lending decision. Should the "
     "discrepancy prove to be other than administrative, or should rectification not be possible, our valuation "
     "may be materially affected and we reserve the right to revise it."),
    ("Under Construction Phase - Granted Area/Housing Program",
     "At the date of our inspection on [date], [community] was still under development. A number of the "
     "surrounding plots were vacant or under construction, and access to the property was via a compacted dirt "
     "road. We have assumed that the community will be completed in accordance with the approved master plan, "
     "including paved roads, infrastructure, utilities and amenities, within a reasonable timeframe. Our opinion "
     "of Market Value reflects the current state of the community and the market’s expectation of its "
     "completion. We have not verified the developer’s delivery timeline. Should the community not be completed "
     "as planned, or should completion be materially delayed, our valuation may be affected."),
]

SPECIAL_ASSUMPTIONS = [
    ("Granted",
     "We understand that the property is held under a granted title. The sale or transfer of granted land "
     "normally requires the prior approval of the Ruler. This approval is discretionary and may be refused. Where "
     "it is given, a fee may be charged, which we understand can be up to 50% of the land value.\n\n"
     "For the purposes of this valuation, we have adopted the Special Assumption that, as at the valuation date, "
     "the property has been converted to private freehold title and can be freely sold or transferred without "
     "approval or the payment of any conversion fee."),
    ("Hotel Apartment",
     "The subject unit is located within [Building Name], which operates as a hotel apartment development. "
     "Owners in developments of this kind may be party to a lease or management agreement with a hotel operator, "
     "under which the unit is included in a rental pool. Such arrangements can limit how the unit may be "
     "occupied, used or sold.\n\n"
     "We understand that the subject unit is subject to an agreement of this nature. However, as agreed with the "
     "client, we have valued the property on the Special Assumption that, as at the valuation date, it is free "
     "from any operator agreement or rental pool arrangement and may be occupied, used and transferred without "
     "restriction.\n\n"
     "The Market Value reported is therefore subject to this Special Assumption. The value of the unit with the "
     "operator agreement in place could be materially different. Any prospective purchaser or lender should "
     "obtain advice from a suitably qualified legal professional on the terms of any such agreement before "
     "proceeding.\n\n"
     "As hotel apartment units within [Building Name] are regularly traded in the open market, we have adopted "
     "the comparable method of valuation."),
    ("Land Value",
     "At the time of our inspection, the plot was occupied by [XXXX building]. As instructed by the client, we "
     "have also reported the value of the land only. To do this, we have adopted the Special Assumption that, as "
     "at the valuation date, the plot is vacant, cleared of all buildings and structures, and available for "
     "development in accordance with the permitted use and planning parameters.\n\n"
     "We have made no allowance for the cost of demolition, site clearance or removal of any existing "
     "improvements, nor for any value they may contribute. The value of the property as it currently exists, "
     "including the existing improvements, may differ materially from the land value reported."),
    ("Illegal Modifications",
     "During our inspection we observed that the property has been modified from its original approved layout, "
     "including [enclosed balcony / additional room / roof extension / removal of walls / conversion of xxxx]. We "
     "have not been provided with evidence of approval from [Dubai Municipality / the master developer / "
     "Trakhees / the relevant authority], and we have assumed that these modifications are unauthorised. We have "
     "not verified this with the relevant authorities.\n\n"
     "No value has been attributed to the unauthorised works, and our valuation does not reflect any cost of "
     "reinstatement, penalties or fines that may be imposed by the relevant authorities. We recommend that the "
     "legal status of the modifications be confirmed with the relevant authorities prior to any transaction or "
     "lending decision."),
]

CONDITIONS = [
    ("Standard Property - Good Condition",
     "The property was observed to be in good condition at the date of inspection, consistent with its age and "
     "use, and we have assumed that it will remain in this condition provided that normal maintenance and repair "
     "are carried out. Our inspection was limited to a visual inspection and does not constitute a building "
     "survey or a test of services. We have not inspected parts of the structure that are covered, unexposed or "
     "inaccessible, and are unable to confirm that they are free from defect."),
    ("Desktop Standard Property - Good Condition",
     "The property has not been inspected, and we have assumed it to be in good condition, consistent with its "
     "age and use, provided that normal maintenance and repair are carried out."),
    ("Previous Inspection",
     "The property was observed to be in good condition at the date of our previous inspection on [date], "
     "consistent with its age and use. The property has not been re-inspected for the purposes of this report, "
     "and we have assumed that its condition remains unchanged, provided that normal maintenance and repair have "
     "been carried out since that date. Our previous inspection was limited to a visual inspection and did not "
     "constitute a building survey or a test of services. We have not inspected parts of the structure that are "
     "covered, unexposed or inaccessible, and are unable to confirm that they are free from defect."),
    ("Minor Maintenance",
     "At the date of inspection, we noted that minor maintenance works are required to the property, as "
     "described below:\n"
     "- [xxxx]\n"
     "- [xxxx]\n\n"
     "Our inspection was limited to a visual inspection, and we are not qualified to advise on the nature, extent "
     "or cost of any repairs or on the structural or building services condition of the property. We recommend "
     "that the Client appoint a suitably qualified building surveyor or engineer to carry out a full survey "
     "before relying on this report for any purpose that depends on the property’s condition. Our valuation "
     "reflects the property in its observed condition, on the basis that the maintenance works noted are minor "
     "and do not materially affect value. If the survey identifies defects or costs not reflected in this "
     "report, our valuation should be referred back to us for review."),
]

SPECIFICATIONS = [
    ("Standard Property",
     "The property is finished to the developer’s standard and specification and no material upgrades or "
     "alterations were noted at the date of inspection."),
    ("Desktop Standard Property",
     "The property has not been inspected, and we are unable to confirm whether any upgrades or alterations have "
     "been made. The property is understood to be finished to the developer’s standard and specification, as "
     "described in [the developer’s unit specification schedule / handover documentation / information provided "
     "by the Client]."),
    ("Modified Property",
     "The property has been modified and differs from the developer’s original standard and specification, and "
     "was observed to be in good condition at the date of inspection. Details of the finishes and fittings are as "
     "described below:\n"
     "- [xxxx]\n"
     "- [xxxx]"),
    ("Custom Built Property",
     "The property is a custom-built property constructed and finished to a good standard and specification. It "
     "was observed to be in good condition at the date of inspection, and the details of its construction, "
     "finishes and fittings are as described below:\n"
     "- [xxxx]\n"
     "- [xxxx]"),
    ("Shell and Core Office",
     "The property is a shell and core unit, delivered to the developer’s base-build standard, comprising the "
     "structure, external envelope and building services connections, with the internal fit-out, finishes and "
     "fixtures to be completed by the occupier. The Property was observed to be in this condition at the date of "
     "inspection."),
    ("Desktop Shell and Core Office",
     "The property is a shell and core unit, understood to be delivered to the developer’s base-build standard, "
     "comprising the structure, external envelope and building services connections, with the internal fit-out, "
     "finishes and fixtures to be completed by the occupier. This description is based on [the developer’s "
     "specification / handover documentation / information provided by the Client], and the property has not "
     "been inspected."),
    ("Fitted Office/Retail",
     "The property is a fitted [office / retail] unit finished to a standard specification, comprising [e.g. "
     "raised flooring, suspended ceilings, partitioning, lighting and air conditioning / shopfront glazing, "
     "flooring, lighting and air conditioning], and was observed to be in [good] condition at the date of "
     "inspection. Further details of the fit-out are as described in [Section X] of this report."),
    ("Desktop Fitted Office/Retail",
     "The property is understood to be a fitted [office / retail] unit finished to a standard specification, "
     "comprising [e.g. raised flooring, suspended ceilings, partitioning, lighting and air conditioning / "
     "shopfront glazing, flooring, lighting and air conditioning]. This description is based on [source of "
     "information], and the property has not been inspected, so we are unable to confirm its current condition "
     "or whether any alterations have been made."),
    ("Previous Inspection",
     "The property was last inspected by [us / name of valuer or firm] on [date of previous inspection], and has "
     "not been re-inspected for the purposes of this report. This report relies on the findings of that "
     "inspection, together with [source of current information, e.g. information provided by the Client / the "
     "developer’s documentation / DLD records], and we have assumed no changes have occurred to the property "
     "since that date."),
]

# Picking this gives an empty box to write the paragraph in.
CUSTOM = ("Custom", "")
