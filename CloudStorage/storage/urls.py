from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("home/", views.home , name="home"),
    path("sign-up/", views.sign_up , name="sign_up"),
    path('login/', views.login_view, name='login'),
    path('otp/', views.otp_view, name='otp'),
    path('logout/', views.logout_view, name='logout'),
    path('activate/<uidb64>/<token>/', views.activate, name='activate'),
    path('my-profile/', views.my_profile, name='my_profile'),
    path("files/my-files/", views.myFilesIndex , name="my_files_index"),
    path("files/shared-files/", views.sharedFilesIndex , name="shared_files_index"),
    path("files/create-file/", views.create_file , name="create_file"),
    path('files/view-file/<uuid:file_uid>/', views.view_file, name='view_file'),
    path('files/delete/<uuid:file_uid>/', views.delete_file, name='delete_file'),
    path('files/<uuid:file_uid>/change-permissions/', views.change_permissions, name='change_permissions'),
    path('files/download/<uuid:file_uid>/', views.download_file, name='download_file'),
    path('all-file-logs/', views.all_file_logs, name='all_file_logs'),
    path('export-all-file-logs/', views.export_all_file_logs, name='export_all_file_logs'),
    path('current-file-logs-list/', views.current_file_logs_list, name='current_file_logs_list'),
    path('current-file-log-details/<uuid:file_uid>/', views.current_file_log_details, name='current_file_log_details'),
    path('export-current-file-logs/<uuid:file_uid>/', views.export_individual_file_logs, name='export_current_file_logs'),
]