library(readxl)
diseases_incidents <- read_excel("~/OneDrive - University of Cambridge/R/Uganda_Incidents/diseases_incidents.xlsx")
View(diseases_incidents)

# Checking the names and correctness

# Load required library
library(ggplot2)

# Create a bar plot to visualize the frequency of each disease with blue color
ggplot(diseases_incidents, aes(x = disease)) +
  geom_bar(fill = "blue", color = "black") +  # Use blue for the bars
  labs(title = "Frequency of Diseases",
       x = "Disease",
       y = "Count") +
  theme_minimal() +
  theme(axis.text.x = element_text(angle = 45, hjust = 1))  # Rotate x-axis labels for better readability

#Obtaining the top 5 diseases in Uganda for the last 15 years

library(dplyr)

# Identify the top 5 diseases by frequency
top_5_diseases <- diseases_incidents %>%
  group_by(disease) %>%
  summarise(count = n()) %>%
  arrange(desc(count)) %>%
  top_n(20, count)
print(top_5_diseases)

## Visualizing

# Load necessary libraries
library(ggplot2)

# Plot the top 5 diseases as a bar plot with 45-degree rotated labels
ggplot(top_5_diseases, aes(x = reorder(disease, -count), y = count)) +
  geom_bar(stat = "identity", fill = "blue") +
  labs(title = "Top 5 Diseases for 15 years in Uganda", x = "Disease", y = "Count") +
  theme_minimal() +
  theme(axis.text.x = element_text(angle = 45, hjust = 1))

##Time-series


# Extract year from date_incident
diseases_incidents$year <- format(as.Date(diseases_incidents$date_incident), "%Y")

# Summarize counts of diseases per year
disease_per_year <- diseases_incidents %>%
  group_by(year, disease) %>%
  summarise(count = n()) %>%
  ungroup()

# Convert year to numeric for better ordering
disease_per_year$year <- as.numeric(disease_per_year$year)

# Plot disease counts per year
ggplot(disease_per_year, aes(x = year, y = count, fill = disease)) +
  geom_bar(stat = "identity", position = "stack") +
  labs(title = "Disease Incidents by Year", x = "Year", y = "Number of Incidents") +
  theme_minimal() +
  theme(axis.text.x = element_text(angle = 45, hjust = 1))

# Top 10 incidents over the years

# Extract year from date_incident
diseases_incidents$year <- format(as.Date(diseases_incidents$date_incident), "%Y")

# Summarize counts of diseases
top_diseases <- diseases_incidents %>%
  group_by(disease) %>%
  summarise(total_count = n()) %>%
  arrange(desc(total_count)) %>%
  slice_head(n = 10)

# Filter for only top 10 diseases in the original dataset
diseases_incidents_top10 <- diseases_incidents %>%
  filter(disease %in% top_diseases$disease)

# Summarize counts of diseases per year for top 10 diseases
disease_per_year_top10 <- diseases_incidents_top10 %>%
  group_by(year, disease) %>%
  summarise(count = n()) %>%
  ungroup()

# Convert year to numeric for better ordering
disease_per_year_top10$year <- as.numeric(disease_per_year_top10$year)

# Plot disease counts per year for top 10 diseases
ggplot(disease_per_year_top10, aes(x = year, y = count, fill = disease)) +
  geom_bar(stat = "identity", position = "stack") +
  labs(title = "Top 10 Disease Incidents by Year", x = "Year", y = "Number of Incidents") +
  theme_minimal() +
  theme(axis.text.x = element_text(angle = 45, hjust = 1))


##Mapping the outbreaks on Uganda's Map

uga_shp_adm1 <- sf::read_sf("~/OneDrive - University of Cambridge/R/Livestock movement/Gravity model developed/uga_admbnda_ubos_20200824_shp/uga_admbnda_adm2_ubos_20200824.shp") 


locations <- as_tibble(uga_shp_adm1 %>%
                         sf::st_centroid(uga_shp_adm1) %>%    
                         select(ADM2_EN) %>%
                         dplyr::mutate(lon = sf::st_coordinates(st_centroid(.))[, 1],
                                       lat = sf::st_coordinates(st_centroid(.))[, 2]))

#Removing the excess the spaces

diseases_incidents$district <- trimws(diseases_incidents$district)
locations$ADM2_EN <- trimws(locations$ADM2_EN)

# Ensuring that both district columns are character type
diseases_incidents$district <- as.character(diseases_incidents$district)
locations$ADM2_EN <- as.character(locations$ADM2_EN)

# left join
diseases_incidents <- diseases_incidents %>%
  left_join(locations, by = c("district" = "ADM2_EN"))

locations_sf <- st_as_sf(locations, coords = c("lon", "lat"), crs = 4326)




##Agreggating the dataset

library(dplyr)

# Aggregate the data by disease and year, counting occurrences
aggregated_data <- diseases_incidents %>%
  group_by(disease, district, year) %>%
  count(name = "number of incidents") %>%  # Create a new column 'count' for the occurrences
  ungroup()  # Ungroup the data for future operations if needed

# Aggregate the data by disease, summing the number of incidents for each disease-year combination
top_10_diseases <- aggregated_data %>%
  group_by(disease, district, year) %>%
  summarise(total_incidents = sum(`number of incidents`)) %>%  # Sum incidents per disease
  arrange(desc(total_incidents)) %>%  # Sort by total incidents in descending order
  top_n(10, total_incidents)  # Select top 10 diseases based on incidents

# View the top 10 diseases
top_10_diseases

# Create the bar plot to visualize the top 10 diseases by total incidents
ggplot(top_10_diseases, aes(x = reorder(disease, total_incidents), y = total_incidents, fill = disease)) +
  geom_bar(stat = "identity") +  # Create a bar plot
  coord_flip() +  # Flip coordinates to make the disease names readable
  labs(
    x = "Disease", 
    y = "Total Number of Incidents") +
  theme_minimal() +  # Use a minimal theme
  theme(legend.position = "none")  # Remove legend if not needed

## More visual

# Visualize the top 10 diseases by number of incidents
ggplot(top_10_diseases %>%
         arrange(desc(total_incidents)) %>%
         head(50), aes(x = reorder(disease, total_incidents), y = total_incidents, fill = disease)) +
  geom_bar(stat = "identity") +
  facet_wrap(~ district + year, scales = "free_y") +
  theme_minimal() +
  coord_flip() +  # Flip coordinates to make the labels readable
  labs(title = "Top 10 Diseases by Total Incidents",
       x = "Disease",
       y = "Total Incidents") +
  theme(legend.position = "none",  # Remove the legend if not necessary
        axis.text.x = element_text(angle = 45, hjust = 1))  # Rotate x-axis labels for readability



##Building a simple machine learning model to predict future disease threats in Uganda

##preparing the dataset

# Extract year from date_incident
diseases_incidents$year <- format(as.Date(diseases_incidents$date_incident), "%Y")

# Aggregate the number of incidents per year for each disease
disease_yearly_counts <- diseases_incidents %>%
  group_by(year, disease) %>%
  summarise(count = n()) %>%
  spread(disease, count, fill = 0)  # Convert to wide format with diseases as columns

# Convert year to numeric
disease_yearly_counts$year <- as.numeric(disease_yearly_counts$year)


# Split the data into training (e.g., until 2020) and testing (future years)
train_data <- filter(disease_yearly_counts, year <= 2021)
test_data <- filter(disease_yearly_counts, year > 2021)

# Remove <NA> column
train_data <- train_data %>%
  select(-`<NA>`)

# Remove grouping to calculate row sums across diseases
train_data_no_group <- train_data %>% ungroup()

# Calculate the total cases per year (sum across disease columns, excluding the 'year' column)
train_data_no_group <- train_data_no_group %>%
  mutate(total_cases = rowSums(select(., -year), na.rm = TRUE))


library(randomForest)

# Separate features and target
X_train <- train_data_no_group[, -c(1, ncol(train_data_no_group))]  # Exclude 'year' and 'total_cases'
y_train <- train_data_no_group$total_cases  # Target is total cases

# Fit the Random Forest model
rf_model <- randomForest(X_train, y_train, ntree = 500)
print(rf_model)

# Plot the importance of each feature
importance(rf_model)
varImpPlot(rf_model)

## Simulating the dataset
# Ensure the 'year' column is numeric and filter the latest year for simulation
simulated_2030 <- train_data %>%
  filter(year == max(year)) %>%  # Get the most recent year
  mutate(across(where(is.numeric), ~ . * 2))  # Double the values for all numeric columns

# Add the year 2030 to the simulated dataset
simulated_2030 <- simulated_2030 %>%
  mutate(year = 2030)

# Pivot the data to long format for easier visualization
simulated_2030_long <- simulated_2030 %>%
  pivot_longer(cols = -year, names_to = "disease", values_to = "cases")

# Visualize the simulated diseases and their predicted occurrences for 2030
ggplot(simulated_2030_long, aes(x = reorder(disease, -cases), y = cases)) +
  geom_bar(stat = "identity", fill = "blue") +
  coord_flip() +  # Flip the x and y axes for better readability
  labs(title = "Simulated Disease Occurrences in 2030 (Twice the Current Occurrences)", 
       x = "Disease", y = "Predicted Number of Cases") +
  theme_minimal() +
  theme(axis.text.x = element_text(angle = 45, hjust = 1))

# Ensure X_2030 has the same structure and column names as the training data
X_2030 <- simulated_2030 %>%
  select(-year) %>%  # Remove the 'year' column
  select(names(X_train))  # Ensure the columns are in the same order as the training data

# Predict the total cases for 2030
predicted_cases_2030 <- predict(rf_model, X_2030)

# Ensure the predicted cases are repeated for each disease
simulated_2030_long$predicted_cases <- rep(predicted_cases_2030, each = nrow(simulated_2030_long) / length(predicted_cases_2030))

# Rank diseases by the predicted number of cases for 2030
top_5_diseases_2030 <- simulated_2030_long %>%
  arrange(desc(predicted_cases)) %>%
  slice_head(n = 10)  # Get top 5 diseases with the highest predicted cases

# Visualize the top 5 predicted diseases in 2030
ggplot(top_5_diseases_2030, aes(x = reorder(disease, -predicted_cases), y = predicted_cases)) +
  geom_bar(stat = "identity", fill = "blue") +
  coord_flip() +  # Flip the axes for better readability
  labs(title = "Top 5 Predicted Diseases for 2030", 
       x = "Disease", y = "Predicted Number of Cases") +
  theme_minimal() +
  theme(axis.text.x = element_text(angle = 45, hjust = 1))


