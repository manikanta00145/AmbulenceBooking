document.addEventListener("DOMContentLoaded", () => {
  const patientCount = document.getElementById("id_number_of_patients");
  const detailFields = document.querySelectorAll(".patient-detail-field");
  if (!patientCount || detailFields.length === 0) return;

  const updatePatientFields = () => {
    const showDetails = patientCount.value === "1";
    detailFields.forEach((field) => {
      field.hidden = !showDetails;
      const input = field.querySelector("input, select");
      if (input) input.required = showDetails;
    });
  };

  patientCount.addEventListener("change", updatePatientFields);
  updatePatientFields();
});
