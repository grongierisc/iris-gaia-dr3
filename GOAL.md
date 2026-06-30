Using the publicly available [Gaia DR3 epoch photometry archives](https://cdn.gea.esac.esa.int/?prefix=Gaia/gdr3/Photometry/epoch_photometry/), identify astronomical objects whose characteristics BP or RP changed by more than 100% over the observation period and generate a list of results.

Description of the columns of Gaia DR3 epoch photometry files available in [Gaia documentation](https://gea.esac.esa.int/archive/documentation/GDR3/Gaia_archive/chap_datamodel/sec_dm_photometry/ssec_dm_epoch_photometry.html). 

 

💡 Update: Based on feedback from early participants, we have defined a standard benchmark dataset for the challenge. All submissions should process only the first 20 files from the Gaia DR3 epoch photometry archive: EpochPhotometry_000000-003111.* through EpochPhotometry_020985-021233.*

 

This ensures that all solutions are evaluated on the same input data while keeping the challenge focused on efficient data ingestion, processing, and analytics.

For each source_id:

    Process the bp_flux and rp_flux arrays
    Ignore missing, null, NaN, or otherwise invalid flux values
    Calculate the minimum (min_flux) and maximum (max_flux) valid flux values for both BP and RP bands across all valid observations
    Calculate the percentage change using the following formula for each band (BP and RP):

Percentage change = ((max_flux − min_flux) / min_flux) × 100

5. Choose the biggest value of the two as resulting percentage_change

The output must include the following data for each astronomical object that satisfies the criteria (calculated percentage change is greater than 100%):

    source_id
    bp_min_flux
    bp_max_flux
    rp_min_flux
    rp_max_flux
    percentage_change

Your submission must

    Be fully functional, scalable and show good performance

    Be Open Source and published on GitHub or GitLab

    Contain README file in English, with the installation steps, and a description of how the application works

    Use InterSystems technologies as the primary implementation platform

Add a script named RunChallenge to the root directory of your repository. This script will be executed automatically using a CI/CD pipeline (GitHub Actions or GitLab CI). It must run without manual input and generate the result containing source_id, bp_min_flux, bp_max_flux, rp_min_flux, rp_max_flux, percentage_change as comma-separated strings, with one record per line.

