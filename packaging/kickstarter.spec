%{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}
Name:       kickstarter
Summary:	Create kickstart files for image creation
Version:    0.17
Release:    1
Group:      Base/Utilities
License:    GPL-2.0
BuildArch:  noarch
URL:        http://www.tizen.org
Source0:    %{name}-%{version}.tar.bz2
Source1001: kickstarter.manifest
Requires:   python-yaml
Requires:   python-cheetah
Requires:   python-lxml
BuildRequires:  python-devel
BuildRequires:  python-cheetah


%description
Create Configuration files(kickstart) to build images


%prep
%setup -q -n %{name}-%{version}


%build
cp %{SOURCE1001} .
make tmpls

CFLAGS="$RPM_OPT_FLAGS" %{__python} setup.py build


%install
rm -rf $RPM_BUILD_ROOT
%if 0%{?suse_version}
%{__python} setup.py install --root=$RPM_BUILD_ROOT --prefix=%{_prefix}
%else
%{__python} setup.py install --root=$RPM_BUILD_ROOT -O1 --prefix=%{_prefix}
%endif


%files
%manifest %{name}.manifest
%defattr(-,root,root,-)
%{_bindir}/*
%{python_sitelib}/*
