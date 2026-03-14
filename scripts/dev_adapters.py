
from dotenv import load_dotenv
import os


from pmd_utils.io.adapters.googledrive import GoogleDriveClient


from pydantic import Field, Secret, BaseModel, field_validator

class SpoConfig(BaseModel):
    tenant_id: str = Field(default=os.getenv("AZURE_TENANT_ID"))
    client_id: str = Field(default=os.getenv("AZURE_CLIENT_ID"))
    client_secret: Secret[str] = Field(default=os.getenv("AZURE_CLIENT_SECRET"))
    scope: list[str] = Field(default=["https://graph.microsoft.com/.default"])
    user_delegated_access: bool = Field(default=False)

    @field_validator("scope",mode="before")
    @classmethod
    def to_list(cls, v):
        if isinstance(v, str):
            return [v]
        return v


class GDriveConfig(BaseModel):
    credentials_path: str = Field(default=os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
    scope: str = Field(default="https://www.googleapis.com/auth/drive")


load_dotenv()

spo_creds = SpoConfig().model_dump()
gdrive_creds = GDriveConfig().model_dump()


# spo = SharepointClient(**spo_creds)
# spo.get_from_weburl("https://norc.sharepoint.com/:x:/r/sites/9877/Shared%20Documents/General/Study%20Management%20Systems/000_Mirrored_Metadata_Repository/migrated-data/drc-migrated-data-dd.xlsx")

gdrive = GoogleDriveClient(**gdrive_creds)

# get_ = gdrive.get_from_weburl("https://docs.google.com/document/d/1lvWns43FFPerUjFpHPFfFnPLr-B-ERAqG83AVC4bpME/edit?usp=sharing")
get_ = gdrive.get_file("1lvWns43FFPerUjFpHPFfFnPLr-B-ERAqG83AVC4bpME")
# download_ = gdrive.download_from_weburl("https://docs.google.com/document/d/1lvWns43FFPerUjFpHPFfFnPLr-B-ERAqG83AVC4bpME/edit?usp=sharing",
#                                         output_path="test.docx"
# )
downloaded_filepath = gdrive.download_file("1lvWns43FFPerUjFpHPFfFnPLr-B-ERAqG83AVC4bpME",
                                 output_path="test.docx"
)
# drive.update_from_weburl("https://docs.google.com/document/d/1lvWns43FFPerUjFpHPFfFnPLr-B-ERAqG83AVC4bpME/edit?usp=sharing",
#                          local_path="test.docx"
# )



update_ = gdrive.update_file(
    file_id="1lvWns43FFPerUjFpHPFfFnPLr-B-ERAqG83AVC4bpME",
    file_in_bytes_or_path="test2.docx"
) # also can use gdrive.update_from_weburl()

# TODO: test create file method