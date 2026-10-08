/**
 * profileData.js
 * Reference lists, dropdown options, and location mappings for the 7-step Citizen Profile Wizard.
 */

export const INDIAN_STATES_DISTRICTS = {
  "Maharashtra": [
    "Ahmednagar", "Akola", "Amravati", "Aurangabad (Chhatrapati Sambhaji Nagar)", "Beed", "Bhandara", "Buldhana",
    "Chandrapur", "Dhule", "Gadchiroli", "Gondia", "Hingoli", "Jalgaon", "Jalna", "Kolhapur", "Latur", "Mumbai City",
    "Mumbai Suburban", "Nagpur", "Nanded", "Nandurbar", "Nashik", "Osmanabad (Dharashiv)", "Palghar", "Parbhani",
    "Pune", "Raigad", "Ratnagiri", "Sangli", "Satara", "Sindhudurg", "Solapur", "Thane", "Wardha", "Washim", "Yavatmal"
  ],
  "Delhi": [
    "Central Delhi", "East Delhi", "New Delhi", "North Delhi", "North East Delhi", "North West Delhi",
    "Shahdara", "South Delhi", "South East Delhi", "South West Delhi", "West Delhi"
  ],
  "Karnataka": [
    "Bagalkot", "Ballari", "Belagavi", "Bengaluru Rural", "Bengaluru Urban", "Bidar", "Chamarajanagar",
    "Chikkaballapur", "Chikkamagaluru", "Chitradurga", "Dakshina Kannada", "Davanagere", "Dharwad", "Gadag",
    "Hassan", "Haveri", "Kalaburagi", "Kodagu", "Kolar", "Koppal", "Mandya", "Mysuru", "Raichur", "Ramanagara",
    "Shivamogga", "Tumakuru", "Udupi", "Uttara Kannada", "Vijayapura", "Yadgir"
  ],
  "Uttar Pradesh": [
    "Agra", "Aligarh", "Ambedkar Nagar", "Amethi", "Amroha", "Auraiya", "Ayodhya", "Azamgarh", "Baghpat",
    "Bahraich", "Ballia", "Balrampur", "Banda", "Barabanki", "Bareilly", "Basti", "Bhadohi", "Bijnor", "Budaun",
    "Bulandshahr", "Chandauli", "Chitrakoot", "Deoria", "Etah", "Etawah", "Farrukhabad", "Fatehpur", "Firozabad",
    "Gautam Buddha Nagar (Noida)", "Ghaziabad", "Ghazipur", "Gonda", "Gorakhpur", "Hamirpur", "Hapur", "Hardoi",
    "Hathras", "Jalaun", "Jaunpur", "Jhansi", "Kannauj", "Kanpur Dehat", "Kanpur Nagar", "Kasganj", "Kaushambi",
    "Kheri", "Kushinagar", "Lalitpur", "Lucknow", "Maharajganj", "Mahoba", "Mainpuri", "Mathura", "Mau", "Meerut",
    "Mirzapur", "Moradabad", "Muzaffarnagar", "Pilibhit", "Pratapgarh", "Prayagraj", "Raebareli", "Rampur",
    "Saharanpur", "Sambhal", "Sant Kabir Nagar", "Shahjahanpur", "Shamli", "Shravasti", "Siddharthnagar",
    "Sitapur", "Sonbhadra", "Sultanpur", "Unnao", "Varanasi"
  ],
  "Gujarat": [
    "Ahmedabad", "Amreli", "Anand", "Aravalli", "Banaskantha", "Bharuch", "Bhavnagar", "Botad", "Chhota Udaipur",
    "Dahod", "Dang", "Devbhumi Dwarka", "Gandhinagar", "Gir Somnath", "Jamnagar", "Junagadh", "Kheda", "Kutch",
    "Mahisagar", "Mehsana", "Morbi", "Narmada", "Navsari", "Panchmahal", "Patan", "Porbandar", "Rajkot",
    "Sabarkantha", "Surat", "Surendranagar", "Tapi", "Vadodara", "Valsad"
  ],
  "Madhya Pradesh": [
    "Agar Malwa", "Alirajpur", "Anuppur", "Ashoknagar", "Balaghat", "Barwani", "Betul", "Bhind", "Bhopal",
    "Burhanpur", "Chhatarpur", "Chhindwara", "Damoh", "Datia", "Dewas", "Dhar", "Dindori", "Guna", "Gwalior",
    "Harda", "Hoshangabad", "Indore", "Jabalpur", "Jhabua", "Katni", "Khandwa", "Khargone", "Mandla", "Mandsaur",
    "Morena", "Narsinghpur", "Neemuch", "Panna", "Raisen", "Rajgarh", "Ratlam", "Rewa", "Sagar", "Satna", "Sehore",
    "Seoni", "Shahdol", "Shajapur", "Sheopur", "Shivpuri", "Sidhi", "Singrauli", "Tikamgarh", "Ujjain", "Umaria", "Vidisha"
  ],
  "Rajasthan": [
    "Ajmer", "Alwar", "Banswara", "Baran", "Barmer", "Bharatpur", "Bhilwara", "Bikaner", "Bundi", "Chittorgarh",
    "Churu", "Dausa", "Dholpur", "Dungarpur", "Hanumangarh", "Jaipur", "Jaisalmer", "Jalore", "Jhalawar", "Jhunjhunu",
    "Jodhpur", "Karauli", "Kota", "Nagaur", "Pali", "Pratapgarh", "Rajsamand", "Sawai Madhopur", "Sikar", "Sirohi",
    "Sri Ganganagar", "Tonk", "Udaipur"
  ],
  "Tamil Nadu": [
    "Ariyalur", "Chengalpattu", "Chennai", "Coimbatore", "Cuddalore", "Dharmapuri", "Dindigul", "Erode",
    "Kallakurichi", "Kanchipuram", "Kanyakumari", "Karur", "Krishnagiri", "Madurai", "Mayiladuthurai", "Nagapattinam",
    "Namakkal", "Nilgiris", "Perambalur", "Pudukkottai", "Ramanathapuram", "Ranipet", "Salem", "Sivaganga", "Tenkasi",
    "Thanjavur", "Theni", "Thoothukudi", "Tiruchirappalli", "Tirunelveli", "Tirupathur", "Tiruppur", "Tiruvallur",
    "Tiruvannamalai", "Tiruvarur", "Vellore", "Viluppuram", "Virudhunagar"
  ],
  "Bihar": [
    "Araria", "Arwal", "Aurangabad", "Banka", "Begusarai", "Bhagalpur", "Bhojpur", "Buxar", "Darbhanga",
    "East Champaran", "Gaya", "Gopalganj", "Jamui", "Jehanabad", "Kaimur", "Katihar", "Khagaria", "Kishanganj",
    "Lakhisarai", "Madhepura", "Madhubani", "Munger", "Muzaffarpur", "Nalanda", "Nawada", "Patna", "Purnia",
    "Rohtas", "Saharsa", "Samastipur", "Saran", "Sheikhpura", "Sheohar", "Sitamarhi", "Siwan", "Supaul", "Vaishali",
    "West Champaran"
  ],
  "West Bengal": [
    "Alipurduar", "Bankura", "Birbhum", "Cooch Behar", "Dakshin Dinajpur", "Darjeeling", "Hooghly", "Howrah",
    "Jalpaiguri", "Jhargram", "Kalimpong", "Kolkata", "Malda", "Murshidabad", "Nadia", "North 24 Parganas",
    "Paschim Bardhaman", "Paschim Medinipur", "Purba Bardhaman", "Purba Medinipur", "Purulia", "South 24 Parganas",
    "Uttar Dinajpur"
  ],
  "Telangana": [
    "Adilabad", "Bhadradri Kothagudem", "Hyderabad", "Jagtial", "Jangaon", "Jayashankar Bhupalpally",
    "Jogulamba Gadwal", "Kamareddy", "Karimnagar", "Khammam", "Kumuram Bheem Asifabad", "Mahabubabad",
    "Mahbubnagar", "Mancherial", "Medak", "Medchal–Malkajgiri", "Mulugu", "Nagarkurnool", "Nalgonda",
    "Narayanpet", "Nirmal", "Nizamabad", "Peddapalli", "Rajanna Sircilla", "Ranga Reddy", "Sangareddy",
    "Siddipet", "Suryapet", "Vikarabad", "Wanaparthy", "Warangal", "Hanamkonda", "Yadadri Bhuvanagiri"
  ],
  "Andhra Pradesh": [
    "Alluri Sitharama Raju", "Anakapalli", "Ananthapuramu", "Annamayya", "Bapatla", "Chittoor", "Dr. B.R. Ambedkar Konaseema",
    "East Godavari", "Eluru", "Guntur", "Kakinada", "Krishna", "Kurnool", "Nandyal", "NTR", "Palnadu", "Parvathipuram Manyam",
    "Prakasam", "Sri Potti Sriramulu Nellore", "Sri Sathya Sai", "Srikakulam", "Tirupati", "Visakhapatnam", "Vizianagaram",
    "West Godavari", "YSR"
  ],
  "Kerala": [
    "Alappuzha", "Ernakulam", "Idukki", "Kannur", "Kasaragod", "Kollam", "Kottayam", "Kozhikode", "Malappuram",
    "Palakkad", "Pathanamthitta", "Thiruvananthapuram", "Thrissur", "Wayanad"
  ],
  "Punjab": [
    "Amritsar", "Barnala", "Bathinda", "Faridkot", "Fatehgarh Sahib", "Fazilka", "Ferozepur", "Gurdaspur",
    "Hoshiarpur", "Jalandhar", "Kapurthala", "Ludhiana", "Malerkotla", "Mansa", "Moga", "Muktsar", "Pathankot",
    "Patiala", "Rupnagar", "Sahibzada Ajit Singh Nagar (Mohali)", "Sangrur", "Shahid Bhagat Singh Nagar", "Tarn Taran"
  ],
  "Haryana": [
    "Ambala", "Bhiwani", "Charkhi Dadri", "Faridabad", "Fatehabad", "Gurugram", "Hisar", "Jhajjar", "Jind",
    "Kaithal", "Karnal", "Kurukshetra", "Mahendragarh", "Nuh", "Palwal", "Panchkula", "Panipat", "Rewari",
    "Rohtak", "Sirsa", "Sonipat", "Yamunanagar"
  ],
  "Other / Union Territory": ["Other District / Regional Unit"]
};

export const INDIAN_STATES = Object.keys(INDIAN_STATES_DISTRICTS);

export const PROFILE_TYPE_OPTIONS = [
  { value: "STUDENT", label: "Student" },
  { value: "FARMER", label: "Farmer" },
  { value: "EMPLOYEE", label: "Employee / Worker" },
  { value: "BUSINESS", label: "Business / Entrepreneur" },
  { value: "SENIOR_CITIZEN", label: "Senior Citizen" },
  { value: "HOMEMAKER", label: "Homemaker" },
  { value: "PWD", label: "Person with Disability" },
  { value: "OTHER", label: "Other" },
];

export const CITIZEN_TYPE_OPTIONS = [
  { value: "GENERAL", label: "General Citizen" },
  { value: "STUDENT", label: "Student" },
  { value: "FARMER", label: "Farmer" },
  { value: "SENIOR", label: "Senior Citizen" },
];

export const GENDER_OPTIONS = [
  { value: "MALE", label: "Male" },
  { value: "FEMALE", label: "Female" },
  { value: "OTHER", label: "Other" },
  { value: "PREFER_NOT_TO_SAY", label: "Prefer not to say" },
];

export const SOCIAL_CATEGORIES = [
  { value: "OPEN", label: "Open / General" },
  { value: "OBC", label: "Other Backward Class (OBC)" },
  { value: "SC", label: "Scheduled Caste (SC)" },
  { value: "ST", label: "Scheduled Tribe (ST)" },
  { value: "EWS", label: "Economically Weaker Section (EWS)" },
  { value: "SBC", label: "Special Backward Class (SBC)" },
  { value: "VJNT", label: "Vimukta Jati / Nomadic Tribes (VJ / NT)" },
  { value: "OTHER", label: "Other" },
];

export const MARITAL_STATUS_OPTIONS = [
  { value: "SINGLE", label: "Single / Unmarried" },
  { value: "MARRIED", label: "Married" },
  { value: "DIVORCED", label: "Divorced" },
  { value: "WIDOWED", label: "Widowed" },
  { value: "SEPARATED", label: "Separated" },
];

export const DISABILITY_STATUS_OPTIONS = [
  { value: "NONE", label: "None / Not Applicable" },
  { value: "PWD_40_PLUS", label: "Person with Disability (40% or more)" },
  { value: "PWD_UNDER_40", label: "Person with Disability (Less than 40%)" },
];

export const DISABILITY_TYPE_OPTIONS = [
  { value: "ORTHOPEDIC", label: "Locomotor / Orthopedic Disability" },
  { value: "VISUAL", label: "Visual Impairment / Blindness" },
  { value: "HEARING", label: "Hearing Impairment / Deaf" },
  { value: "SPEECH", label: "Speech and Language Disability" },
  { value: "INTELLECTUAL", label: "Intellectual Disability" },
  { value: "MENTAL_ILLNESS", label: "Mental Illness" },
  { value: "MULTIPLE", label: "Multiple Disabilities" },
  { value: "OTHER", label: "Other Disability" },
];

export const EMPLOYMENT_STATUS_OPTIONS = [
  { value: "EMPLOYED", label: "Employed (Private / Corporate)" },
  { value: "GOVERNMENT_EMPLOYEE", label: "Government Employee" },
  { value: "SELF_EMPLOYED", label: "Self Employed / Freelancer" },
  { value: "BUSINESS_OWNER", label: "Business Owner / Entrepreneur" },
  { value: "FARMER", label: "Farmer / Agricultural Worker" },
  { value: "DAILY_WAGE", label: "Daily Wage / Informal Worker" },
  { value: "STUDENT", label: "Student" },
  { value: "UNEMPLOYED", label: "Unemployed" },
  { value: "RETIRED", label: "Retired / Pensioner" },
  { value: "HOMEMAKER", label: "Homemaker" },
];

export const INCOME_SOURCE_OPTIONS = [
  { value: "SALARY", label: "Salary / Wages" },
  { value: "AGRICULTURE", label: "Agriculture / Farming" },
  { value: "BUSINESS", label: "Business / Trade" },
  { value: "PENSION", label: "Pension / Retirement Benefits" },
  { value: "DAILY_LABOUR", label: "Daily Wage Labour" },
  { value: "RENTAL_INVESTMENT", label: "Rent / Investments" },
  { value: "OTHER", label: "Other" },
];

export const POVERTY_CATEGORY_OPTIONS = [
  { value: "APL", label: "Above Poverty Line (APL)" },
  { value: "BPL", label: "Below Poverty Line (BPL)" },
  { value: "EWS", label: "Economically Weaker Section (EWS)" },
  { value: "AAY", label: "Antyodaya Anna Yojana (AAY)" },
  { value: "NOT_SURE", label: "Not Applicable / Not Sure" },
];

export const AREA_TYPE_OPTIONS = [
  { value: "RURAL", label: "Rural" },
  { value: "URBAN", label: "Urban" },
  { value: "SEMI_URBAN", label: "Semi-Urban" },
];

export const EDUCATION_LEVEL_OPTIONS = [
  { value: "10TH_SSC", label: "10th / SSC" },
  { value: "12TH_HSC", label: "12th / HSC" },
  { value: "DIPLOMA", label: "Diploma / Polytechnic" },
  { value: "ITI", label: "ITI (Industrial Training)" },
  { value: "UNDERGRADUATE", label: "Undergraduate / Bachelor's Degree" },
  { value: "POSTGRADUATE", label: "Postgraduate / Master's Degree" },
  { value: "PHD", label: "PhD / Doctorate" },
  { value: "OTHER", label: "Other Qualification" },
];

export const SSC_BOARD_OPTIONS = [
  { value: "MAHARASHTRA_STATE_BOARD", label: "Maharashtra State Board (MSBSHSE)" },
  { value: "CBSE", label: "CBSE (Central Board of Secondary Education)" },
  { value: "ICSE", label: "ICSE / CISCE" },
  { value: "OTHER_STATE_BOARD", label: "Other State Board" },
  { value: "NIOS", label: "National Institute of Open Schooling (NIOS)" },
];

export const HSC_STREAM_OPTIONS = [
  { value: "SCIENCE", label: "Science" },
  { value: "COMMERCE", label: "Commerce" },
  { value: "ARTS", label: "Arts / Humanities" },
  { value: "VOCATIONAL", label: "Vocational / MCVC" },
  { value: "OTHER", label: "Other" },
];

export const UG_DEGREE_OPTIONS = [
  { value: "B_TECH_BE", label: "B.Tech / B.E. (Engineering)" },
  { value: "B_SC", label: "B.Sc (Bachelor of Science)" },
  { value: "B_COM", label: "B.Com (Bachelor of Commerce)" },
  { value: "B_A", label: "B.A. (Bachelor of Arts)" },
  { value: "BCA", label: "BCA (Computer Applications)" },
  { value: "BBA_BMS", label: "BBA / BMS (Management)" },
  { value: "MBBS_BDS", label: "MBBS / BDS (Medical)" },
  { value: "B_PHARM", label: "B.Pharm (Pharmacy)" },
  { value: "B_ARCH", label: "B.Arch (Architecture)" },
  { value: "LLB", label: "LL.B. (Law)" },
  { value: "OTHER_UG", label: "Other Bachelor's Degree" },
];

export const PG_DEGREE_OPTIONS = [
  { value: "M_TECH_ME", label: "M.Tech / M.E." },
  { value: "M_SC", label: "M.Sc" },
  { value: "M_COM", label: "M.Com" },
  { value: "M_A", label: "M.A." },
  { value: "MCA", label: "MCA" },
  { value: "MBA", label: "MBA / MMS" },
  { value: "MD_MS", label: "MD / MS" },
  { value: "M_PHARM", label: "M.Pharm" },
  { value: "LLM", label: "LL.M." },
  { value: "OTHER_PG", label: "Other Master's Degree" },
];

export const CURRENT_YEAR_OPTIONS = [
  { value: "FIRST_YEAR", label: "1st Year (FY)" },
  { value: "SECOND_YEAR", label: "2nd Year (SY)" },
  { value: "THIRD_YEAR", label: "3rd Year (TY)" },
  { value: "FOURTH_YEAR", label: "4th Year (Final Year)" },
  { value: "FIFTH_YEAR", label: "5th Year" },
];

export const RESULT_STATUS_OPTIONS = [
  { value: "PASSED", label: "Passed" },
  { value: "APPEARED", label: "Appeared / Awaiting Result" },
  { value: "PURSUING", label: "Currently Pursuing" },
  { value: "FAILED", label: "Failed" },
];

export const WIZARD_STEPS = [
  { id: 1, name: "Basic Info", description: "Identity & Personal Details" },
  { id: 2, name: "Education", description: "Qualifications & Current Study" },
  { id: 3, name: "Family & Income", description: "Financial & Household" },
  { id: 4, name: "Social Category", description: "Caste, Disability & Special Status" },
  { id: 5, name: "Location", description: "State, District & Residence" },
  { id: 6, name: "Additional Info", description: "Occupation & Category Specifics" },
  { id: 7, name: "Review & Submit", description: "Verify & Complete Profile" },
];
